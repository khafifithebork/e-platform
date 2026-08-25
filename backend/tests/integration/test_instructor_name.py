"""The instructor's public name, on every surface that shows a course card.

This exists because the field was **silently absent** from every catalogue
response for the whole of M3 through M11. `PublicCourseSerializer` declared
`CharField(source="instructor.get_full_name")`; `User` has no such method; and
because the field was `read_only`, DRF raised `SkipField` rather than erroring.
A serializer that quietly drops a field looks exactly like one that never
declared it, and no test asserted the key.

So the assertions here are about the **key being present**, not only about its
value. `test_the_key_is_present_even_with_no_name` is the one that would have
caught the original bug; every value assertion below would have passed happily
against a response missing the field entirely, because they never looked.
"""

from __future__ import annotations

import pytest

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _course(slug="spanish", title="Spanish Basics", *, name: str | None = "Aoife O'Brien"):
    """A published course whose instructor may or may not have a profile.

    `name=None` means no `InstructorProfile` row at all, which is the state
    every instructor is in today — nothing has ever created one.
    """
    from django.utils import timezone

    from apps.accounts.models import InstructorProfile, Role
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, CourseStatus, Language
    from apps.catalog.services import refresh_search_vector

    instructor = create_account(email=f"{slug}-teacher@example.test", password=PASSWORD)
    instructor.role = Role.INSTRUCTOR
    instructor.save(update_fields=["role"])
    if name is not None:
        InstructorProfile.objects.create(user=instructor, display_name=name)

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Espanol"}
    )
    course = Course.objects.create(
        slug=slug, title=title, language=language, level="A1", instructor=instructor
    )
    Course.objects.filter(pk=course.pk).update(
        status=CourseStatus.PUBLISHED, published_at=timezone.now()
    )
    course.refresh_from_db()
    refresh_search_vector(course=course)
    return course


class TestItAppearsOnEverySurface:
    def test_the_catalogue_list(self, client) -> None:
        _course()

        card = client.get("/api/v1/catalogue/courses/").json()["results"][0]

        assert card["instructor_name"] == "Aoife O'Brien"

    def test_the_course_detail(self, client) -> None:
        course = _course()

        body = client.get(f"/api/v1/catalogue/courses/{course.slug}/").json()

        assert body["instructor_name"] == "Aoife O'Brien"

    def test_search_results(self, client) -> None:
        _course()

        results = client.get("/api/v1/catalogue/search/", {"q": "spanish"}).json()["results"]

        assert results[0]["instructor_name"] == "Aoife O'Brien"

    def test_the_related_strip(self, client) -> None:
        """The strip renders through the same serializer, so it is the surface
        most likely to be forgotten when this changes."""
        course = _course()
        _course(slug="neighbour", title="Spanish More", name="Someone Else")

        related = client.get(f"/api/v1/catalogue/courses/{course.slug}/").json()["related"]

        assert related[0]["instructor_name"] == "Someone Else"


class TestWhenThereIsNoName:
    def test_the_key_is_present_even_with_no_profile(self, client) -> None:
        """**The test that would have caught the original bug.** Every value
        assertion above passes against a response with the key missing, because
        they never check for it."""
        _course(name=None)

        card = client.get("/api/v1/catalogue/courses/").json()["results"][0]

        assert "instructor_name" in card
        assert card["instructor_name"] == ""

    def test_and_with_a_profile_that_has_a_blank_name(self, client) -> None:
        """Blank is allowed and means "nothing to show". The client is told
        that, rather than left to infer it from an absent key."""
        _course(name="")

        card = client.get("/api/v1/catalogue/courses/").json()["results"][0]

        assert card["instructor_name"] == ""

    def test_the_address_is_never_used_as_a_fallback(self, client) -> None:
        """The catalogue is unauthenticated. An email address on a public page
        is a spam list, which is why the original serializer reached for a name
        rather than the address in the first place."""
        _course(name=None)

        raw = client.get("/api/v1/catalogue/courses/").content.decode()

        assert "@example.test" not in raw


class TestItCostsNoQueryPerCourse:
    def test_the_catalogue_list_stays_flat(self, client) -> None:
        """ADR-009: two dataset sizes, identical counts. Rendering a name off a
        related profile is the textbook N+1, and it is invisible until the
        catalogue has more than a handful of rows."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _course(slug="first")
        with CaptureQueriesContext(connection) as small:
            assert client.get("/api/v1/catalogue/courses/").status_code == 200

        for index in range(5):
            _course(slug=f"more-{index}")
        with CaptureQueriesContext(connection) as large:
            assert client.get("/api/v1/catalogue/courses/").status_code == 200

        assert len(large.captured_queries) == len(small.captured_queries), (
            f"{len(small.captured_queries)} queries for 1 course, "
            f"{len(large.captured_queries)} for 6"
        )


class TestItCanActuallyBeSet:
    def test_the_admin_exposes_the_name(self) -> None:
        """A field nothing can write is a field that is always empty. There is
        no instructor-facing profile API and adding one would be an endpoint
        with no caller, so Django Admin is the interface — the same call M10
        §2.5 made."""
        from django.contrib import admin as django_admin

        from apps.accounts.models import InstructorProfile

        model_admin = django_admin.site._registry[InstructorProfile]

        assert "display_name" in model_admin.fields

    def test_the_approval_trail_is_not_editable_there(self) -> None:
        """Approval is an act with a record, not a checkbox on a profile
        form."""
        from django.contrib import admin as django_admin

        from apps.accounts.models import InstructorProfile

        model_admin = django_admin.site._registry[InstructorProfile]

        assert "approved_at" not in model_admin.fields
        assert "approved_by" not in model_admin.fields
