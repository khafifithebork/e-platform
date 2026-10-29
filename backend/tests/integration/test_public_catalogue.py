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

        # The course, its sections, their lessons, and M11's related strip.
        # Four regardless of how many sections exist — that is what the
        # prefetch buys, and the fourth is one query however many related
        # courses come back, which `test_related_courses.py` pins at two
        # dataset sizes.
        with django_assert_num_queries(4):
            client.get(f"{CATALOGUE}{course.slug}/")


class TestTotalDuration:
    """Roadmap E8's duration half. ADR-041.

    The decision under test is not the sum — it is **when a sum may be
    published at all.** A course with one unmeasured lesson advertising the
    other nine lessons' minutes as its total is a wrong number presented as a
    fact, and §6 is about exactly that.
    """

    def _lesson(self, course, position: int, *, duration, lesson_type=None):
        """A lesson, with a measured asset when `duration` is given.

        `duration=None` means an asset exists but the provider has not
        reported a length yet — the transcoding-in-progress case, which is the
        one that matters. `duration=False` means no asset at all.
        """
        from apps.catalog.models import Lesson, LessonType, Section
        from apps.media_assets.models import MediaAsset, MediaAssetStatus

        section = Section.objects.create(
            course=course, title=f"Section {position}", position=position
        )
        lesson = Lesson.objects.create(
            course=course,
            section=section,
            slug=f"lesson-{position}",
            title=f"Lesson {position}",
            position=1,
            lesson_type=lesson_type or LessonType.VIDEO,
        )
        if duration is not False:
            MediaAsset.objects.create(
                lesson=lesson,
                source_object_key=f"masters/{position}/a.mp4",
                source_bytes=2048,
                status=MediaAssetStatus.PENDING,
                duration_seconds=duration,
            )
        return lesson

    def _duration(self, client, course):
        return client.get(f"{CATALOGUE}{course.slug}/").json()["total_duration_seconds"]

    def test_a_fully_measured_course_reports_the_sum(self, client, language) -> None:
        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        self._lesson(course, 2, duration=900)

        assert self._duration(client, course) == 1500

    def test_one_unmeasured_lesson_withholds_the_whole_total(self, client, language) -> None:
        """The decision. Not 600 — that would advertise a one-lesson course's
        length as a two-lesson course's total."""
        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        self._lesson(course, 2, duration=None)

        assert self._duration(client, course) is None

    def test_a_lesson_with_no_asset_also_withholds_it(self, client, language) -> None:
        """A lesson nobody has uploaded to is as unmeasured as one still
        transcoding, and the learner cannot tell the difference anyway."""
        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        self._lesson(course, 2, duration=False)

        assert self._duration(client, course) is None

    def test_a_course_with_no_lessons_is_null_rather_than_zero(self, client, language) -> None:
        """A course with no lessons yet, and a course zero minutes long, are
        different claims. Only one of them is true."""
        course = _course(language, "published", "PUBLISHED")

        assert self._duration(client, course) is None

    def test_the_field_is_always_present(self, client, language) -> None:
        """Null, not absent. A key that disappears when the value is unknown
        makes the client infer the difference between "no duration" and "old
        API" — the failure `get_instructor_name` documents."""
        course = _course(language, "published", "PUBLISHED")

        assert "total_duration_seconds" in client.get(f"{CATALOGUE}{course.slug}/").json()

    def test_another_courses_lessons_are_not_counted(self, client, language) -> None:
        """The join is per course. A `Sum` over a shared path that aggregated
        the whole catalogue would still look right on a one-course fixture."""
        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        other = _course(language, "other", "PUBLISHED")
        self._lesson(other, 1, duration=99999)

        assert self._duration(client, course) == 600

    def test_duration_costs_no_extra_query(
        self, client, language, django_assert_num_queries
    ) -> None:
        """The annotation must fold into the course query rather than add one.
        Same four as `TestQueryCount` above, with the aggregate in place."""
        course = _course(language, "published", "PUBLISHED")
        for position in range(1, 4):
            self._lesson(course, position, duration=300)

        with django_assert_num_queries(4):
            client.get(f"{CATALOGUE}{course.slug}/")

    def test_a_text_lesson_does_not_withhold_the_total(self, client, language) -> None:
        """Found by review, and it was a real defect rather than a nit.

        A TEXT lesson never gets a `MediaAsset`, so counting it as something
        awaiting measurement made completeness unreachable: the course withheld
        its total **forever** instead of until its videos were measured.
        """
        from apps.catalog.models import LessonType

        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        self._lesson(course, 2, duration=False, lesson_type=LessonType.TEXT)

        assert self._duration(client, course) == 600

    def test_a_resource_lesson_does_not_withhold_it_either(self, client, language) -> None:
        from apps.catalog.models import LessonType

        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=900)
        self._lesson(course, 2, duration=False, lesson_type=LessonType.RESOURCE)

        assert self._duration(client, course) == 900

    def test_an_audio_lesson_counts_toward_the_total(self, client, language) -> None:
        """Audio is measurable too — it is a language-learning product, and an
        audio-only lesson has a length like any other."""
        from apps.catalog.models import LessonType

        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        self._lesson(course, 2, duration=300, lesson_type=LessonType.AUDIO)

        assert self._duration(client, course) == 900

    def test_an_unmeasured_audio_lesson_still_withholds_it(self, client, language) -> None:
        """The exemption is by lesson type, not a blanket one: a measurable
        lesson nobody has measured still suppresses the total."""
        from apps.catalog.models import LessonType

        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)
        self._lesson(course, 2, duration=None, lesson_type=LessonType.AUDIO)

        assert self._duration(client, course) is None

    def test_a_course_of_only_text_lessons_is_null(self, client, language) -> None:
        """Nothing measurable is not the same as zero minutes."""
        from apps.catalog.models import LessonType

        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=False, lesson_type=LessonType.TEXT)

        assert self._duration(client, course) is None

    def test_the_catalogue_card_does_not_carry_it(self, client, language) -> None:
        """Deliberately detail-only: the annotation adds a GROUP BY and two
        joins, and the list, filter and search querysets all build on
        `published_courses`. Pinned so adding it to the card is a decision
        somebody makes rather than a side effect."""
        course = _course(language, "published", "PUBLISHED")
        self._lesson(course, 1, duration=600)

        card = client.get(CATALOGUE).json()["results"][0]

        assert "total_duration_seconds" not in card
