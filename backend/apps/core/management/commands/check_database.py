"""Ask a database whether it can host this application, before migrating it.

**Written for one specific unknown.** ADR-023 §M12 handover:

    "`CREATE EXTENSION pg_trgm` is verified locally, not on Neon. It ran
    against a live Postgres for the first time in T7, as superuser `app`. A
    managed provider may not grant it."

`catalog.0005_search_vector` installs that extension, and its own docstring
explains the placement — "so that a missing `CREATE EXTENSION` privilege fails
at the migration that installs it rather than at the query that needs it". That
is the right place to fail, and it is still an expensive place to find out:
the migration is `atomic = False`, because `CREATE INDEX CONCURRENTLY` requires
it, so a failure part-way can leave an `INVALID` index that must be dropped by
hand before a retry.

So this asks the question first, changing nothing. Run it against a database
before `predeploy` touches it — a Neon branch, a staging box, anything.

**The capability probe rolls back.** Where an extension is absent, this creates
it inside a transaction and then aborts, which answers "may this role install
it" without installing it. `CREATE EXTENSION` is transactional in PostgreSQL,
unlike `CREATE INDEX CONCURRENTLY` — that difference is exactly why the real
migration cannot be atomic and this check can be.

Exit codes, because this is meant to be run by a person reading a terminal and
by a pipeline that is not:

    0   this database can host the application
    1   something the application requires is missing or not permitted
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction

# Extensions the application cannot work without, and what breaks first.
#
# One entry today. It is a list rather than a constant because the next one
# will be added by somebody who is not thinking about this file, and a list
# invites an entry where a constant invites a second check somewhere else.
REQUIRED_EXTENSIONS: tuple[tuple[str, str], ...] = (
    (
        "pg_trgm",
        "trigram search — a typo stops finding the course it meant (M11, ADR-020 §4)",
    ),
)


class Command(BaseCommand):
    help = "Check that a database can host this application. Changes nothing."

    def handle(self, *args, **options) -> None:
        problems: list[str] = []

        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.execute("SELECT current_user, current_database()")
            role, database = cursor.fetchone()

        self.stdout.write(f"database: {database}")
        self.stdout.write(f"role:     {role}")
        self.stdout.write(f"server:   {version.split(' on ')[0]}")
        self.stdout.write("")

        for name, consequence in REQUIRED_EXTENSIONS:
            problems.extend(self._check_extension(name, consequence))

        self.stdout.write("")
        if problems:
            for problem in problems:
                self.stdout.write(self.style.ERROR(f"  {problem}"))
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "This database cannot host the application as it stands. "
                    "Fix the above before running `predeploy` — a failed migration "
                    "here is expensive, because 0005_search_vector is not atomic."
                )
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("This database can host the application."))

    def _check_extension(self, name: str, consequence: str) -> list[str]:
        """Installed, or installable by this role? Report which, change neither."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = %s", [name])
            if cursor.fetchone():
                self.stdout.write(self.style.SUCCESS(f"{name}: installed"))
                return self._check_trigram_works() if name == "pg_trgm" else []

            # Not present. Ask whether this role could install it, without
            # leaving it installed — the answer is what a managed provider
            # might withhold, and finding out during `migrate` is the
            # expensive way to learn it.
            cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = %s", [name])
            if not cursor.fetchone():
                return [f"{name}: not available on this server at all. Without it: {consequence}."]

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'CREATE EXTENSION "{name}"')
                # Roll back rather than commit. This is a question, not a
                # migration — `0005_search_vector` is what installs it, and two
                # things installing one extension is one of them being wrong.
                raise _ProbeSucceeded
        except _ProbeSucceeded:
            self.stdout.write(
                self.style.WARNING(f"{name}: not installed, but this role may install it")
            )
            return []
        except Exception as error:  # the message is the finding, whatever it is
            return [f"{name}: this role may not install it — {error}. Without it: {consequence}."]

    def _check_trigram_works(self) -> list[str]:
        """Installed is not the same as usable.

        An extension present in `pg_extension` but installed into a schema this
        role's `search_path` does not reach answers every catalogue query with
        "function similarity(text, text) does not exist" — which reads as a
        code bug rather than a configuration one.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT similarity('spanish', 'spamish')")
                score = cursor.fetchone()[0]
        except Exception as error:  # the message is the finding, whatever it is
            return [f"pg_trgm: installed but unusable from this role — {error}."]

        self.stdout.write(f"pg_trgm: usable (similarity('spanish','spamish') = {score:.2f})")
        return []


class _ProbeSucceeded(Exception):
    """Rolls the probe back. Not an error — the only way out of `atomic` that
    undoes the statement, since committing would install the extension this
    command exists to avoid installing."""
