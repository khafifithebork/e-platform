"""The public catalogue.

Abuse cases 5 and 6. Every "it is not visible" test here has a twin that
publishes the same course and watches it appear, because a status filter that
matched *nothing* would satisfy the negative cases perfectly and ship an empty
catalogue. ADR-006 is usually about a control that permits too much; this is
the same failure wearing the opposite mask.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

CATALOGUE = "/api/v1/catalogue/courses/"
LANGUAGES = "/api/v1/catalogue/languages/"
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


@pytest.fixture
def language(db):
    from apps.catalog.models import Language

    return Language.objects.create(code="es", name="Spanish", native_name="Español")


def _course(language, slug: str, status: str):
    """A course in a given state, published through the real transitions.

    Never by writing `status` directly: a course forced to PUBLISHED without
    `published_at` is a row the database constraint forbids, so a test that
    built one would be asserting against a state production cannot reach.
    """
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, CourseStatus
    from apps.catalog.services import approve, archive, submit_for_review

    instructor = create_account(email=f"{slug}@example.test", password=PASSWORD)
    instructor.role = Role.INSTRUCTOR
    instructor.save(update_fields=["role"])

    admin = create_account(email=f"admin-{slug}@example.test", password=PASSWORD)
    admin.role = Role.ADMIN
    admin.save(update_fields=["role"])

    course = Course.objects.create(
        slug=slug, title=slug.title(), language=language, level="A1", instructor=instructor
    )
    if status == CourseStatus.DRAFT:
        return course

    submit_for_review(course=course, by=instructor)
    if status == CourseStatus.IN_REVIEW:
        return course

    approve(course=course, by=admin)
    if status == CourseStatus.PUBLISHED:
        return course

    archive(course=course, by=admin)
    return course


@pytest.mark.parametrize("status", ["DRAFT", "IN_REVIEW", "ARCHIVED"])
class TestOnlyPublishedCoursesAreVisible:
    """Abuse cases 5 and 6, once per state that must stay hidden."""

    def test_it_is_absent_from_the_list(self, client, language, status) -> None:
        _course(language, "hidden", status)

        slugs = {row["slug"] for row in client.get(CATALOGUE).json()["results"]}

        assert slugs == set()

    def test_its_slug_is_a_404(self, client, language, status) -> None:
        course = _course(language, "hidden", status)

        assert client.get(f"{CATALOGUE}{course.slug}/").status_code == 404


class TestPublishedCoursesAreVisible:
    """The twins. Without these, a filter matching nothing passes every test
    above and ships an empty catalogue."""

    def test_a_published_course_is_listed(self, client, language) -> None:
        _course(language, "published", "PUBLISHED")

        slugs = {row["slug"] for row in client.get(CATALOGUE).json()["results"]}

        assert slugs == {"published"}

    def test_a_published_course_is_readable_by_slug(self, client, language) -> None:
        course = _course(language, "published", "PUBLISHED")

        response = client.get(f"{CATALOGUE}{course.slug}/")

        assert response.status_code == 200
        assert response.json()["slug"] == "published"

    def test_archiving_removes_it_again(self, client, language) -> None:
        """Provokes the filter in both directions in one test: the same course
        is visible, then is not, with nothing changing but its status."""
        from apps.accounts.services import create_account
        from apps.catalog.services import archive

        course = _course(language, "published", "PUBLISHED")
        assert client.get(f"{CATALOGUE}{course.slug}/").status_code == 200

        admin = create_account(email="closer@example.test", password=PASSWORD)
        admin.role = Role.ADMIN
        admin.save(update_fields=["role"])
        archive(course=course, by=admin)

        assert client.get(f"{CATALOGUE}{course.slug}/").status_code == 404


class TestItIsGenuinelyPublic:
    def test_no_authentication_is_required(self, client, language) -> None:
        """DRF denies by default, so the exemption has to be deliberate — and
        being deliberate, it has to be tested."""
        _course(language, "published", "PUBLISHED")

        assert client.get(CATALOGUE).status_code == 200
        assert client.get(LANGUAGES).status_code == 200

    def test_languages_with_nothing_published_are_not_offered(self, client, language) -> None:
        """A filter option that returns an empty page is a dead end for the
        visitor and a free enumeration of what is being worked on."""
        from apps.catalog.models import Language

        Language.objects.create(code="ar", name="Arabic", native_name="العربية")
        _course(language, "published", "PUBLISHED")

        codes = {row["code"] for row in client.get(LANGUAGES).json()}

        assert codes == {"es"}


class TestPaidContentIsNotServed:
    def test_lesson_bodies_are_absent_from_the_detail(self, client, language) -> None:
        """Entitlements do not exist until M4, so there is nothing to gate
        with. The field is omitted rather than conditionally hidden: a field
        that is usually hidden is one bug from being visible."""
        from apps.catalog.models import Lesson, Section

        course = _course(language, "published", "PUBLISHED")
        section = Section.objects.create(course=course, title="Greetings", position=1)
        Lesson.objects.create(
            course=course,
            section=section,
            slug="intro",
            title="Intro",
            body="The paid content.",
            position=1,
        )

        response = client.get(f"{CATALOGUE}{course.slug}/")

        assert b"The paid content." not in response.content
        lesson = response.json()["sections"][0]["lessons"][0]
        assert "body" not in lesson
        assert lesson["title"] == "Intro"

    def test_the_curriculum_structure_is_still_shown(self, client, language) -> None:
        """The shape of the course is the sales pitch — hiding it entirely
        would be as wrong as leaking the content."""
        from apps.catalog.models import Lesson, Section

        course = _course(language, "published", "PUBLISHED")
        for position, title in enumerate(["Greetings", "Numbers"], start=1):
            section = Section.objects.create(course=course, title=title, position=position)
            Lesson.objects.create(
                course=course,
                section=section,
                slug=f"lesson-{position}",
                title=f"Lesson {position}",
                position=1,
            )

        sections = client.get(f"{CATALOGUE}{course.slug}/").json()["sections"]

        assert [section["title"] for section in sections] == ["Greetings", "Numbers"]


class TestQueryCount:
    def test_the_list_does_not_fan_out(self, client, language, django_assert_num_queries) -> None:
        """Abuse case 9, and §6.2's denial-of-service line: a catalogue page
        that fans out per card is the cheapest way to load the database from
        an unauthenticated request."""
        for index in range(5):
            _course(language, f"course-{index}", "PUBLISHED")

        # Exactly one. No count query — the API paginates by cursor, which
        # never asks how many rows there are — and no session or user lookup,
        # because the view declares no authentication classes. Five cards for
        # one query is the number to defend when the catalogue page grows.
        with django_assert_num_queries(1):
            client.get(CATALOGUE)

    def test_the_detail_does_not_fan_out_per_section(
        self, client, language, django_assert_num_queries
    ) -> None:
        """The selector claims a prefetch saves a query per section. Measured
        rather than asserted, because that claim is the kind that quietly stops
        being true when someone adds a field to the serializer."""
        from apps.catalog.models import Lesson, Section

        course = _course(language, "published", "PUBLISHED")
        for position in range(1, 6):
            section = Section.objects.create(
                course=course, title=f"Section {position}", position=position
            )
            Lesson.objects.create(
                course=course,
                section=section,
                slug=f"lesson-{position}",
                title=f"Lesson {position}",
                position=1,
            )

        # The course, its sections, their lessons. Three regardless of how many
        # sections exist — that is what the prefetch buys.
        with django_assert_num_queries(3):
            client.get(f"{CATALOGUE}{course.slug}/")
