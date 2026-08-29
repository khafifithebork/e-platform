"""Everything that must happen between a new image existing and it serving.

**A management command rather than a script, because of where it has to run.**
The backend image is built from `backend/` as its context, so nothing in the
repository's `scripts/` directory is inside it. A pre-deploy step that lives
there can be invoked by CI and by nothing else; this one is available wherever
the image is, which is the whole point — `render.yaml`, a Dokploy job, a
Kubernetes init container and `docker compose run` can all call the same thing,
and none of them has to know what it does.

That matters more than it sounds: CLAUDE.md §11 #4 leaves the hosting target
open, and a deploy step shaped around one platform is a decision made by
accident.

Three things it does, in order, and the order is the design:

1. **Wait for the database**, bounded. A platform starts a container the moment
   the image is pulled, which is routinely before the database accepts
   connections. Failing instantly there means a deploy that would have
   succeeded is marked failed.
2. **Take an advisory lock.** Two replicas rolled out together both run their
   pre-deploy step, and `migrate` is not safe to run twice concurrently — two
   transactions can both decide a migration is unapplied. Postgres advisory
   locks are held for the session and released when it ends, including when
   the process is killed, so a crashed deploy cannot leave the lock held.
3. **Apply migrations**, and only migrations.

**It deliberately does not run backfills.** Invariant 14 puts those in separate,
idempotent, chunked commands precisely so they are not part of the critical
path of a deploy — a backfill that touches every row must be watchable and
interruptible, and a deploy step is neither.

It also does not run `check --deploy`. That is a different question — is this
configuration sane — and answering it here would mean a misconfiguration is
discovered after the lock is taken.
"""

from __future__ import annotations

import time
import zlib

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor

# A fixed 63-bit key. Derived from a string rather than written as a magic
# number so that a second lock added later is obviously a different one, and
# `pg_locks` can be read against a value somebody can reproduce.
LOCK_KEY = zlib.crc32(b"e-platform:predeploy") & 0x7FFFFFFF

DEFAULT_DB_WAIT_SECONDS = 60
DEFAULT_LOCK_WAIT_SECONDS = 300


class Command(BaseCommand):
    help = "Wait for the database, take a deploy lock, and apply migrations."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report pending migrations and exit non-zero if any. Applies nothing.",
        )
        parser.add_argument("--db-wait", type=int, default=DEFAULT_DB_WAIT_SECONDS)
        parser.add_argument("--lock-wait", type=int, default=DEFAULT_LOCK_WAIT_SECONDS)

    def handle(self, *args, **options) -> None:
        connection = connections[DEFAULT_DB_ALIAS]

        self._wait_for_database(connection, seconds=options["db_wait"])

        pending = self._pending_migrations(connection)
        if not pending:
            self.stdout.write(self.style.SUCCESS("No migrations to apply."))
            return

        self.stdout.write(f"{len(pending)} migration(s) pending:")
        for app_label, name in pending:
            self.stdout.write(f"  {app_label}.{name}")

        if options["check"]:
            # Non-zero on purpose. `--check` exists so a pipeline can ask "does
            # this release need a migration step" and branch on the answer.
            raise CommandError("Migrations are pending.")

        with self._deploy_lock(connection, seconds=options["lock_wait"]):
            call_command("migrate", "--noinput", verbosity=options.get("verbosity", 1))

        self.stdout.write(self.style.SUCCESS("Migrations applied."))

    def _wait_for_database(self, connection, *, seconds: int) -> None:
        """Poll until the database answers, or give up loudly.

        Polling rather than a single attempt because a platform starts the
        container as soon as the image is pulled. Bounded rather than forever
        because a deploy that hangs is worse than one that fails: the first
        needs somebody to notice, the second tells them.
        """
        deadline = time.monotonic() + seconds
        attempt = 0
        while True:
            attempt += 1
            try:
                connection.ensure_connection()
            # Broad on purpose: every driver signals "not listening yet"
            # differently, and a narrower catch here would turn a database
            # that is merely slow to start into a failed deploy.
            except Exception as exc:
                if time.monotonic() >= deadline:
                    raise CommandError(
                        f"Database unreachable after {seconds}s ({attempt} attempts): {exc}"
                    ) from exc
                self.stdout.write(f"Database not ready (attempt {attempt}); retrying.")
                time.sleep(2)
            else:
                return

    def _pending_migrations(self, connection) -> list[tuple[str, str]]:
        """Which migrations this release would apply.

        Read through Django's own executor rather than by comparing files, so
        the answer matches what `migrate` would actually do.
        """
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        return [
            (migration.app_label, migration.name)
            for migration, _ in executor.migration_plan(targets)
        ]

    def _require_a_real_session(self, connection) -> None:
        """Confirm the lock we just took is actually held by this backend.

        **A transaction-mode connection pooler makes this lock a no-op**, and
        does it silently. Neon's documentation lists "session-level advisory
        locks" among the features its pooler does not support, and recommends a
        direct connection for schema migrations — *"Tools may not support
        transaction pooling"*. PgBouncer in transaction mode returns the server
        connection to the pool after each statement, so the next statement can
        land on a different backend: `pg_try_advisory_lock` returns true, the
        lock is attached to a connection nobody holds, and a second deploy is
        told it may proceed.

        The whole point of this lock is that two rollouts cannot migrate at
        once. Losing it quietly is worse than not having it, because the
        docstring above still claims it is there.

        Checked by asking rather than by inspecting the hostname. Sniffing for
        `-pooler` in a connection string tests one provider's naming
        convention; this tests the property the lock needs — that the session
        holding it is the session we are in.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM pg_locks
                WHERE locktype = 'advisory' AND objid = %s AND pid = pg_backend_pid()
                """,
                [LOCK_KEY],
            )
            held = cursor.fetchone()[0]

        if not held:
            raise CommandError(
                "The migration lock was granted but is not held by this backend. "
                "That is what a transaction-mode connection pooler does to a "
                "session-level advisory lock: it reports success and serialises "
                "nothing. "
                "Run migrations over a direct, unpooled connection. On Neon that "
                "is the connection string without `-pooler` in the host; the "
                "application may keep using the pooled one."
            )

    def _deploy_lock(self, connection, *, seconds: int):
        """A Postgres advisory lock, so concurrent deploys serialise.

        Session-scoped, so it is released when the connection closes — including
        when the process is killed. A lock held in a table would need a timeout
        and a way to break it; this one cannot outlive the thing holding it.
        """
        command = self

        class _Lock:
            def __enter__(self):
                deadline = time.monotonic() + seconds
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
                        if cursor.fetchone()[0]:
                            command._require_a_real_session(connection)
                            return self
                    if time.monotonic() >= deadline:
                        raise CommandError(
                            f"Another deploy has held the migration lock for {seconds}s. "
                            "It may be stuck, or a migration may be genuinely long-running."
                        )
                    command.stdout.write("Waiting for the migration lock.")
                    time.sleep(2)

            def __exit__(self, *exc_info):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
                return False

        return _Lock()
