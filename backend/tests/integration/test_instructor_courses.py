"""The instructor course API.

`architecture.md` §10 names the mistake for this milestone: "letting
instructors query courses without a `get_queryset()` scope filter. Write the
IDOR test first." These were written before the view existed.

§6.3 adds the part that is easy to get wrong. An object the caller is not
scoped to must answer **404**, not 403 — a 403 says "this exists and is not
yours", which is exactly the fact being protected.
"""

from __future__ import annotations

import pytest
from django.db import DatabaseError, connection

from apps.accounts.models import Role

COURSES = "/api/v1/instructor/courses/"
PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _instructor(email: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def language(db):
    from apps.catalog.models import Language

    return Language.objects.create(code="es", name="Spanish", native_name="Español")


@pytest.fixture
def mine(db, language):
    from apps.catalog.models import Course

    return Course.objects.create(
        slug="mine",
        title="Mine",
        language=language,
        level="A1",
        instructor=_instructor("me@example.test"),
    )


@pytest.fixture
def theirs(db, language):
    from apps.catalog.models import Course

    return Course.objects.create(
        slug="theirs",
        title="Theirs",
        language=language,
        level="A1",
        instructor=_instructor("them@example.test"),
    )


def _sign_in(client, email: str):
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


@pytest.mark.django_db
class TestScoping:
    """Abuse cases 1 and 2."""

    def test_the_list_shows_only_your_own_courses(self, client, mine, theirs) -> None:
        _sign_in(client, "me@example.test")

        body = client.get(COURSES).json()
        slugs = {row["slug"] for row in body["results"]}

        assert slugs == {"mine"}

    def test_reading_someone_elses_course_is_a_404(self, client, mine, theirs) -> None:
        """Not 403. A 403 confirms the course exists (§6.3)."""
        _sign_in(client, "me@example.test")

        assert client.get(f"{COURSES}{theirs.id}/").status_code == 404

    def test_editing_someone_elses_course_is_a_404_and_changes_nothing(
        self, client, mine, theirs
    ) -> None:
        _sign_in(client, "me@example.test")

        response = client.patch(
            f"{COURSES}{theirs.id}/", {"title": "Hijacked"}, content_type="application/json"
        )

        assert response.status_code == 404
        theirs.refresh_from_db()
        assert theirs.title == "Theirs"

    def test_delete_is_unavailable_without_disclosing_course_existence(
        self, client, mine, theirs
    ) -> None:
        from apps.catalog.models import Course

        _sign_in(client, "me@example.test")

        # DELETE is no longer an action, even for the owner (ADR-039).
        foreign = client.delete(f"{COURSES}{theirs.id}/")
        missing = client.delete(f"{COURSES}00000000-0000-0000-0000-000000000000/")
        assert foreign.status_code == missing.status_code == 405
        assert foreign.json() == missing.json()
        assert Course.objects.filter(pk=theirs.pk).exists()

    def test_anonymous_callers_are_refused(self, client, mine) -> None:
        assert client.get(COURSES).status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("course_status", ["DRAFT", "IN_REVIEW", "PUBLISHED", "ARCHIVED"])
def test_instructor_delete_is_unavailable(client, mine, course_status) -> None:
    from django.utils import timezone

    from apps.catalog.models import Course

    mine.status = course_status
    mine.published_at = timezone.now() if course_status == "PUBLISHED" else None
    mine.save(update_fields=["status", "published_at"])
    _sign_in(client, "me@example.test")
    url = f"{COURSES}{mine.pk}/"

    response = client.delete(url)

    assert response.status_code == 405
    assert "DELETE" not in response["Allow"]
    assert Course.objects.filter(pk=mine.pk, status=course_status).exists()
    assert "DELETE" not in client.options(url)["Allow"]


@pytest.mark.django_db
class TestCreation:
    def test_a_course_is_owned_by_its_creator(self, client, language) -> None:
        """The instructor is taken from the session, never from the body."""
        from apps.catalog.models import Course

        author = _instructor("me@example.test")
        other = _instructor("them@example.test")
        _sign_in(client, "me@example.test")

        response = client.post(
            COURSES,
            {
                "slug": "new-course",
                "title": "New course",
                "language": language.pk,
                "level": "A1",
                # An attempt to assign it to someone else.
                "instructor": str(other.id),
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        assert Course.objects.get(slug="new-course").instructor == author

    def test_a_new_course_is_a_draft(self, client, language) -> None:
        _instructor("me@example.test")
        _sign_in(client, "me@example.test")

        response = client.post(
            COURSES,
            {"slug": "new-course", "title": "New", "language": language.pk, "level": "A1"},
            content_type="application/json",
        )

        assert response.json()["status"] == "DRAFT"


@pytest.mark.django_db(transaction=True)
class TestCourseWriteAtomicity:
    @staticmethod
    def fail_search_write(execute, sql, params, many, context):
        if sql.startswith('UPDATE "catalog_course" SET "search_vector"'):
            raise DatabaseError("Synthetic search write failure")
        return execute(sql, params, many, context)

    def test_creation_rolls_back_when_search_refresh_fails(self, client, language) -> None:
        from apps.catalog.models import Course

        _instructor("me@example.test")
        _sign_in(client, "me@example.test")

        with connection.execute_wrapper(self.fail_search_write), pytest.raises(DatabaseError):
            client.post(
                COURSES,
                {"slug": "atomic-create", "title": "New", "language": language.pk, "level": "A1"},
                content_type="application/json",
            )

        assert not Course.objects.filter(slug="atomic-create").exists()

    def test_update_rolls_back_when_search_refresh_fails(self, client, mine) -> None:
        _sign_in(client, "me@example.test")

        with connection.execute_wrapper(self.fail_search_write), pytest.raises(DatabaseError):
            client.patch(
                f"{COURSES}{mine.id}/",
                {"title": "Should not persist"},
                content_type="application/json",
            )

        mine.refresh_from_db()
        assert mine.title == "Mine"

    def test_partial_edit_returns_persisted_fields_and_refreshes_search(self, client, mine) -> None:
        from django.contrib.postgres.search import SearchQuery

        from apps.catalog.models import Course

        _sign_in(client, "me@example.test")
        response = client.patch(
            f"{COURSES}{mine.id}/",
            {"description": "Portuguese pronunciation", "skill_areas": ["listening"]},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(mine.pk)
        assert response.json()["title"] == "Mine"
        assert response.json()["description"] == "Portuguese pronunciation"
        mine.refresh_from_db()
        assert mine.skill_areas == ["listening"]
        assert Course.objects.filter(pk=mine.pk, search_vector=SearchQuery("portuguese")).exists()
        assert Course.objects.filter(pk=mine.pk, search_vector=SearchQuery("listening")).exists()

    def test_full_edit_changes_content_but_not_ownership_or_publication(self, client, mine) -> None:
        from apps.catalog.models import Language

        other = _instructor("other@example.test")
        french = Language.objects.create(code="fr", name="French")
        _sign_in(client, "me@example.test")
        response = client.put(
            f"{COURSES}{mine.id}/",
            {
                "slug": "french-course",
                "title": "French course",
                "description": "Pronunciation",
                "language": french.pk,
                "level": "B2",
                "skill_areas": ["speaking"],
                "instructor": str(other.pk),
                "status": "PUBLISHED",
                "published_at": "2026-01-01T00:00:00Z",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["slug"] == "french-course"
        assert response.json()["title"] == "French course"
        mine.refresh_from_db()
        assert mine.language_id == french.pk
        assert mine.level == "B2"
        assert mine.instructor_id != other.pk
        assert mine.status == "DRAFT"
        assert mine.published_at is None


@pytest.mark.django_db
class TestStatusIsNotWritable:
    """Abuse case 4 — the one that would hand an instructor the publish button."""

    def test_status_in_the_creation_body_is_ignored(self, client, language) -> None:
        from apps.catalog.models import Course

        _instructor("me@example.test")
        _sign_in(client, "me@example.test")

        client.post(
            COURSES,
            {
                "slug": "sneaky",
                "title": "Sneaky",
                "language": language.pk,
                "level": "A1",
                "status": "PUBLISHED",
                "published_at": "2020-01-01T00:00:00Z",
            },
            content_type="application/json",
        )

        course = Course.objects.get(slug="sneaky")
        assert course.status == "DRAFT"
        assert course.published_at is None

    def test_status_in_a_patch_is_ignored(self, client, mine) -> None:
        _sign_in(client, "me@example.test")

        client.patch(
            f"{COURSES}{mine.id}/",
            {"status": "PUBLISHED"},
            content_type="application/json",
        )

        mine.refresh_from_db()
        assert mine.status == "DRAFT"


@pytest.mark.django_db
class TestSubmitForReview:
    def test_the_owner_may_submit(self, client, mine) -> None:
        _sign_in(client, "me@example.test")

        response = client.post(f"{COURSES}{mine.id}/submit-for-review/")

        assert response.status_code == 200
        mine.refresh_from_db()
        assert mine.status == "IN_REVIEW"

    def test_submitting_someone_elses_course_is_a_404(self, client, mine, theirs) -> None:
        _sign_in(client, "me@example.test")

        assert client.post(f"{COURSES}{theirs.id}/submit-for-review/").status_code == 404
        theirs.refresh_from_db()
        assert theirs.status == "DRAFT"

    def test_submitting_twice_is_a_conflict_not_a_crash(self, client, mine) -> None:
        _sign_in(client, "me@example.test")
        client.post(f"{COURSES}{mine.id}/submit-for-review/")

        second = client.post(f"{COURSES}{mine.id}/submit-for-review/")

        assert second.status_code == 409

    def test_there_is_no_publish_endpoint(self, client, mine) -> None:
        """The instructor API must offer no route to PUBLISHED at all."""
        _sign_in(client, "me@example.test")

        for path in ("publish", "approve"):
            assert client.post(f"{COURSES}{mine.id}/{path}/").status_code == 404


@pytest.mark.django_db
class TestQueryCount:
    def test_the_list_does_not_fan_out(self, client, mine, django_assert_num_queries) -> None:
        """Each card needs its language and instructor; without a join that is
        two extra queries per course."""
        from apps.catalog.models import Course

        for index in range(5):
            Course.objects.create(
                slug=f"extra-{index}",
                title=f"Extra {index}",
                language=mine.language,
                level="A1",
                instructor=mine.instructor,
            )
        _sign_in(client, "me@example.test")

        # Session, user, and one for the page itself.
        with django_assert_num_queries(3):
            client.get(COURSES)
