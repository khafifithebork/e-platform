"""The stored search vector, and the one way it can go stale.

ADR-020 §3 chose a column written by one function over a database trigger. The
trigger cannot drift and this can, so the drift is not left as a footnote —
`test_a_direct_save_leaves_it_stale` provokes it and pins what happens, which
is ADR-011's rule applied at the moment the field gains meaning: when a field
starts being read by something, re-audit every path that writes it, in the
same change.

The weights are asserted rather than assumed. A vector built with the default
weight ranks a course whose *description* mentions Spanish above one titled
"Spanish", and no functional test would notice — the search still returns both.
"""

from __future__ import annotations

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


def _course(**overrides):
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, Language

    language, _ = Language.objects.get_or_create(
        code=overrides.pop("code", "es"),
        defaults={"name": "Spanish", "native_name": "Espanol"},
    )
    instructor = overrides.pop("instructor", None) or create_account(
        email=f"teacher-{Course.objects.count()}@example.test",
        password="a-long-enough-passphrase",
    )
    fields = {
        "slug": "spanish-basics",
        "title": "Spanish Basics",
        "description": "An introduction.",
        "level": "A1",
        "skill_areas": ["listening"],
    }
    fields.update(overrides)
    return Course.objects.create(language=language, instructor=instructor, **fields)


class TestItIsWrittenByTheService:
    def test_a_new_course_has_no_vector_until_it_is_refreshed(self) -> None:
        """Stated rather than assumed. `Course.objects.create` does not know
        about search, which is the whole reason the refresher exists and the
        reason a backfill command has to."""
        course = _course()

        course.refresh_from_db()
        assert course.search_vector is None

    def test_refreshing_populates_it(self) -> None:
        from apps.catalog.services import refresh_search_vector

        course = _course()

        refresh_search_vector(course=course)

        course.refresh_from_db()
        assert course.search_vector is not None

    def test_it_is_refreshed_when_a_title_changes(self, client) -> None:
        """Through the API, which is the write path a learner's search actually
        depends on."""
        from django.contrib.postgres.search import SearchQuery

        from apps.accounts.models import Role
        from apps.accounts.services import create_account
        from apps.catalog.models import Course

        instructor = create_account(email="owner@example.test", password="a-long-enough-passphrase")
        instructor.role = Role.INSTRUCTOR
        instructor.save(update_fields=["role"])
        course = _course(instructor=instructor)

        client.post(
            "/api/v1/auth/login/",
            {"email": "owner@example.test", "password": "a-long-enough-passphrase"},
            content_type="application/json",
        )
        response = client.patch(
            f"/api/v1/instructor/courses/{course.id}/",
            {"title": "Portuguese Basics"},
            content_type="application/json",
        )

        assert response.status_code == 200

        # Asserted by matching, not by reading the stored string. The English
        # configuration stems, so the column holds `portugues` — a test looking
        # for `portuguese` fails against a vector that is completely correct,
        # and would have to be rewritten the day the config changes.
        assert Course.objects.filter(pk=course.pk, search_vector=SearchQuery("portuguese")).exists()
        assert not Course.objects.filter(
            pk=course.pk, search_vector=SearchQuery("spanish")
        ).exists()

    def test_a_direct_save_leaves_it_stale(self) -> None:
        """The chosen design's known limit, provoked rather than described.

        ADR-020 §3 took a service-written column over a trigger, accepting that
        a writer which bypasses the service drifts. This is what that looks
        like. If this test ever starts failing, somebody added a trigger or a
        `save()` override, and the ADR needs rewriting rather than the test.
        """
        from apps.catalog.models import Course
        from apps.catalog.services import refresh_search_vector

        course = _course(title="Spanish Basics")
        refresh_search_vector(course=course)

        Course.objects.filter(pk=course.pk).update(title="Japanese Basics")

        course.refresh_from_db()
        assert "japanes" not in str(course.search_vector).lower()
        assert "spanish" in str(course.search_vector).lower()


class TestTheWeights:
    def test_the_title_outranks_the_description(self) -> None:
        """Weight A over C. Without it a course that merely mentions a word
        ranks alongside one named for it, and every functional test still
        passes because both are returned."""
        from django.contrib.postgres.search import SearchQuery, SearchRank
        from django.db.models import F

        from apps.catalog.models import Course
        from apps.catalog.services import refresh_search_vector

        # Built so that only the weights can decide. The mentioning course
        # says the word *twice*, so on term frequency alone it wins; the named
        # course says it once, in the title. A first version of this test used
        # one mention each and passed with every weight flattened to D — it was
        # measuring nothing, which is ADR-006's failure in a ranking function.
        named = _course(slug="named", title="Portuguese", description="Nothing here.")
        mentions = _course(
            slug="mentions",
            title="General Course",
            description="Portuguese practice, and more Portuguese.",
        )
        for course in (named, mentions):
            refresh_search_vector(course=course)

        ranked = list(
            Course.objects.annotate(rank=SearchRank(F("search_vector"), SearchQuery("portuguese")))
            .filter(search_vector=SearchQuery("portuguese"))
            .order_by("-rank")
            .values_list("slug", flat=True)
        )

        assert ranked[0] == "named", ranked

    def test_skill_areas_are_searchable(self) -> None:
        from django.contrib.postgres.search import SearchQuery

        from apps.catalog.models import Course
        from apps.catalog.services import refresh_search_vector

        course = _course(skill_areas=["pronunciation", "listening"])
        refresh_search_vector(course=course)

        found = Course.objects.filter(search_vector=SearchQuery("pronunciation"))

        assert found.filter(pk=course.pk).exists()


class TestTheDatabaseObjects:
    def test_the_gin_index_exists(self) -> None:
        """Measured against `pg_indexes`, not asserted from the model's Meta.
        A migration that was written but never applied would satisfy the
        model-level check and none of the queries. ADR-009."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'catalog_course' AND indexname = %s",
                ["course_search_vector_gin"],
            )
            row = cursor.fetchone()

        assert row is not None, "the GIN index is not in the database"
        assert "gin" in row[0].lower()

    def test_the_trigram_extension_is_available(self) -> None:
        """T3's fallback needs it. Asserted here so a missing extension fails
        at the task that installs it rather than the task that uses it.

        **Verify separately on Neon.** `CREATE EXTENSION` requires privileges
        the local superuser has and a managed provider may not; this passing
        says nothing about production.
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            assert cursor.fetchone() is not None


class TestTheBackfill:
    def test_it_populates_rows_that_have_none(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        from apps.catalog.models import Course

        course = _course()
        assert Course.objects.get(pk=course.pk).search_vector is None

        call_command("backfill_search_vectors", stdout=StringIO())

        assert Course.objects.get(pk=course.pk).search_vector is not None

    def test_it_is_idempotent(self) -> None:
        """Invariant 14: a backfill is a chunked, idempotent management
        command. Running it twice is the cheap proof of the second half."""
        from io import StringIO

        from django.core.management import call_command

        from apps.catalog.models import Course

        course = _course()
        call_command("backfill_search_vectors", stdout=StringIO())
        first = Course.objects.get(pk=course.pk).search_vector

        call_command("backfill_search_vectors", stdout=StringIO())

        assert Course.objects.get(pk=course.pk).search_vector == first

    def test_it_reports_what_it_did(self) -> None:
        """A backfill nobody can see the result of is one nobody can tell
        finished."""
        from io import StringIO

        from django.core.management import call_command

        _course()
        out = StringIO()

        call_command("backfill_search_vectors", stdout=out)

        assert "1" in out.getvalue()
