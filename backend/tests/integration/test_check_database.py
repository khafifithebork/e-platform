"""The preflight check. M13 T8.

**One unknown made this worth building.** ADR-023's M12 handover:

    "`CREATE EXTENSION pg_trgm` is verified locally, not on Neon. It ran
    against a live Postgres for the first time in T7, as superuser `app`. A
    managed provider may not grant it."

Neon's own documentation says pg_trgm is supported and is not among the
extensions needing support enablement — `pg_repack` and `pg_cron` are named as
those, and pg_trgm is not. That lowers the risk and does not close it, because
"documented as supported" and "this role may install it in this project" are
different sentences.

**The path that matters is the one the development database cannot show.** It
has the extension installed as a superuser, so every check passes trivially
there. The tests that earn their place drop it inside the test transaction —
the same technique M14 T3 used on a unique constraint — and exercise the
branches a managed provider would actually take.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.db import connection

pytestmark = pytest.mark.django_db


def _extension_installed(name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = %s", [name])
        return cursor.fetchone() is not None


def _drop_trigram() -> None:
    """Remove pg_trgm for the duration of one test.

    CASCADE, because `course_search_vector_gin` depends on it — dropping the
    extension without dropping the index is not something PostgreSQL will do.
    pytest-django rolls the whole transaction back, so both come back.
    """
    with connection.cursor() as cursor:
        cursor.execute("DROP EXTENSION pg_trgm CASCADE")


def _run() -> tuple[str, int]:
    """Run the command, returning its output and exit code."""
    out = io.StringIO()
    try:
        call_command("check_database", stdout=out)
    except SystemExit as exit_signal:
        return out.getvalue(), int(exit_signal.code or 0)
    return out.getvalue(), 0


class TestAHealthyDatabase:
    def test_it_passes(self) -> None:
        output, code = _run()

        assert code == 0
        assert "can host the application" in output

    def test_it_says_which_database_and_role(self) -> None:
        """The output is read by somebody who has just pointed this at a
        connection string. Naming the database and role is how they find out
        they pointed it at the wrong one."""
        output, _ = _run()

        assert "database:" in output
        assert "role:" in output

    def test_it_proves_trigram_search_works_rather_than_assuming(self) -> None:
        """Installed is not usable. An extension in `pg_extension` but outside
        this role's `search_path` answers every catalogue query with "function
        similarity(text, text) does not exist" — which reads as a code bug
        rather than a configuration one."""
        output, _ = _run()

        assert "usable" in output
        assert "similarity" in output


class TestWhenTheExtensionIsAbsent:
    """The branch a managed provider would take, and the reason this exists."""

    def test_it_reports_that_the_role_may_install_it(self) -> None:
        _drop_trigram()

        output, code = _run()

        assert code == 0
        assert "may install it" in output

    def test_and_leaves_it_absent(self) -> None:
        """**The probe rolls back**, and that is the whole design.

        Installing the extension here would make the check a migration, and
        `catalog.0005_search_vector` is what installs it — two things
        installing one extension is one of them being wrong. It would also
        make the check pass on second run for a role that could not have
        installed it, which is worse than useless.
        """
        _drop_trigram()
        assert _extension_installed("pg_trgm") is False

        _run()

        assert _extension_installed("pg_trgm") is False

    def test_the_drop_really_happened(self) -> None:
        """The twin. Both assertions above are about a database with no
        pg_trgm, and would pass just as well against one where the DROP
        silently did nothing."""
        assert _extension_installed("pg_trgm") is True

        _drop_trigram()

        assert _extension_installed("pg_trgm") is False


class TestWhenSomethingIsMissing:
    def test_an_unavailable_extension_fails_the_check(self, monkeypatch) -> None:
        """A server that does not ship an extension at all — which is what a
        cut-down managed image looks like."""
        from apps.core.management.commands import check_database

        monkeypatch.setattr(
            check_database,
            "REQUIRED_EXTENSIONS",
            (("no_such_extension", "nothing, it is imaginary"),),
        )

        output, code = _run()

        assert code == 1
        assert "not available on this server" in output

    def test_it_says_what_breaks_rather_than_only_what_is_missing(self, monkeypatch) -> None:
        """ "pg_trgm is missing" tells somebody to install pg_trgm. "a typo
        stops finding the course it meant" tells them whether to hold the
        deploy, which is the decision they are actually making."""
        from apps.core.management.commands import check_database

        monkeypatch.setattr(
            check_database,
            "REQUIRED_EXTENSIONS",
            (("no_such_extension", "trigram search stops tolerating typos"),),
        )

        output, _ = _run()

        assert "trigram search stops tolerating typos" in output

    def test_the_failure_points_at_the_cost_of_finding_out_later(self, monkeypatch) -> None:
        """The reason to run this before `predeploy` rather than instead of it:
        `0005_search_vector` is `atomic = False`, so a failure part-way can
        leave an INVALID index that must be dropped by hand."""
        from apps.core.management.commands import check_database

        monkeypatch.setattr(
            check_database,
            "REQUIRED_EXTENSIONS",
            (("no_such_extension", "nothing"),),
        )

        output, _ = _run()

        assert "not atomic" in output


class TestItChangesNothing:
    def test_a_healthy_database_is_untouched(self) -> None:
        """Stated as its own test because the command's whole promise is that
        it is safe to point at anything, including production."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_extension")
            before = cursor.fetchone()[0]

        _run()

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_extension")
            after = cursor.fetchone()[0]

        assert after == before
