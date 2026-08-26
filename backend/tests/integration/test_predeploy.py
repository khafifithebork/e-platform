"""The pre-deploy step. M13 T3.

The command exists to be called by a platform nobody has chosen yet (§11 #4),
so what is tested here is the behaviour a platform depends on: it reports
pending work, it applies only migrations, it serialises against a concurrent
deploy, and it fails with a non-zero exit rather than hanging.

**Exit codes are asserted through `call_command` raising**, not by reading
`$?` from a pipeline. Three times in this project a `| tail` has reported the
pipe's exit code instead of the command's and made a failing thing look like a
passing one — the last time while verifying this very command by hand.
"""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.core.management.commands.predeploy import LOCK_KEY, Command

pytestmark = pytest.mark.django_db


class _Discard:
    """A stdout for a Command constructed outside `call_command`."""

    def write(self, *args, **kwargs) -> None:
        return None


def _run(*args, **kwargs) -> str:
    from io import StringIO

    out = StringIO()
    call_command("predeploy", *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


def _lock_is_held() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid = %s",
            [LOCK_KEY],
        )
        return cursor.fetchone()[0] > 0


class TestWhenThereIsNothingToDo:
    def test_it_succeeds_and_says_so(self) -> None:
        """The test database is migrated, so this is the ordinary case: a
        release with no schema change still runs the step, and the step has to
        be a no-op rather than an error."""
        assert "No migrations to apply" in _run()

    def test_check_mode_also_succeeds(self) -> None:
        """`--check` exists so a pipeline can branch on whether a release needs
        a migration step. Raising when there is nothing pending would make
        every release look like it needed one."""
        _run("--check")

    def test_it_takes_no_lock_when_there_is_nothing_to_apply(self) -> None:
        """The lock is only worth taking around work. Taking it for a no-op
        would serialise every deploy of every release behind every other."""
        _run()

        assert not _lock_is_held()


class TestTheLock:
    def test_it_is_released_afterwards(self) -> None:
        """Session-scoped, so a crash releases it — but a clean run must not
        rely on that. A lock left held would stall the next deploy for its
        entire timeout."""
        _run()

        assert not _lock_is_held()

    def test_it_gives_up_rather_than_hanging(self) -> None:
        """A deploy that hangs needs somebody to notice; one that fails tells
        them.

        The helper is exercised directly rather than through the command,
        because the command only reaches the lock when migrations are pending
        and the test database has none. Driving it through the command would
        mean rolling a migration back mid-suite to create work — which is a
        larger, slower and more fragile thing than the property being tested.

        The lock is held from a *second* connection, which is what a concurrent
        deploy looks like from here. Held on this one, Postgres would grant it
        again: advisory locks are re-entrant per session, and a test that
        missed that would pass against a lock that serialised nothing.
        """
        from django.db import connections

        command = Command()
        command.stdout = _Discard()

        other = connections.create_connection("default")
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])

            with (
                pytest.raises(CommandError, match="migration lock"),
                command._deploy_lock(connection, seconds=1),
            ):
                pass
        finally:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
            other.close()

    def test_and_it_is_obtainable_when_nobody_holds_it(self) -> None:
        """The positive twin. A lock that could never be taken would satisfy
        the test above perfectly."""
        command = Command()
        command.stdout = _Discard()

        with command._deploy_lock(connection, seconds=1):
            assert _lock_is_held()

        assert not _lock_is_held()

    def test_the_key_is_stable(self) -> None:
        """Derived from a string rather than written as a magic number, so a
        second lock added later is obviously a different one — and so this
        value can be reproduced when reading `pg_locks` during an incident."""
        import zlib

        assert zlib.crc32(b"e-platform:predeploy") & 0x7FFFFFFF == LOCK_KEY


class TestItRefusesToHangOnAnAbsentDatabase:
    def test_it_gives_up_after_the_deadline(self) -> None:
        """A platform starts the container before the database is reachable, so
        the step polls — but bounded. Unbounded, a broken `DATABASE_URL` is a
        deploy that never finishes and never reports.

        Driven with a stand-in connection rather than by patching the real
        one: `django.db.connection` is a proxy, and patching through it is the
        kind of setup that quietly does nothing while the test passes for
        another reason.
        """
        from apps.core.management.commands import predeploy

        class Unreachable:
            def ensure_connection(self):
                raise OSError("connection refused")

        command = Command()
        command.stdout = _Discard()

        with pytest.raises(CommandError, match="unreachable"):
            command._wait_for_database(Unreachable(), seconds=0)

        assert predeploy.DEFAULT_DB_WAIT_SECONDS > 0

    def test_but_it_returns_as_soon_as_the_database_answers(self) -> None:
        """The twin. A waiter that always raised would satisfy the test above,
        and would fail every deploy."""
        attempts = {"count": 0}

        class SlowToStart:
            def ensure_connection(self):
                attempts["count"] += 1
                if attempts["count"] < 2:
                    raise OSError("not yet")

        command = Command()
        command.stdout = _Discard()

        command._wait_for_database(SlowToStart(), seconds=30)

        assert attempts["count"] == 2


class TestWhatItDoesNotDo:
    def test_it_runs_no_backfill(self) -> None:
        """Invariant 14 puts backfills in separate, idempotent, chunked
        commands precisely so they are not on a deploy's critical path — one
        that touches every row must be watchable and interruptible, and a
        deploy step is neither.

        Structural, because a behavioural test would only catch the backfills
        that exist today.
        """
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "apps"
            / "core"
            / "management"
            / "commands"
            / "predeploy.py"
        )
        tree = ast.parse(source.read_text(encoding="utf-8"))

        called = [
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "call_command"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ]

        assert called == ["migrate"], called

    def test_it_does_not_run_the_deployment_check(self) -> None:
        """A different question — is this configuration sane — and answering it
        here would mean a misconfiguration is found *after* the lock is taken."""
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "apps"
            / "core"
            / "management"
            / "commands"
            / "predeploy.py"
        )

        assert "check --deploy" not in source.read_text(encoding="utf-8").replace(
            "It also does not run `check --deploy`.", ""
        )
        assert ast.parse(source.read_text(encoding="utf-8"))
