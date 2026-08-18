"""Query counts on every list endpoint. Abuse case 9.

The usual form of this test — ``assert_num_queries(3)`` over a fixture with one
row — proves a number and nothing else. It passes just as happily when the
endpoint fans out, because with one row a fan-out costs one query. So every
test here runs the same endpoint over a small dataset and a larger one and
asserts the count is **identical**, then pins the absolute value. The first
assertion is the one that means "does not fan out"; the second stops the
number drifting upwards unnoticed.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Role

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


def _instructor(email: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


def _admin(email: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def course(db):
    from apps.catalog.models import Course, Language

    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    return Course.objects.create(
        slug="course",
        title="Course",
        language=language,
        level="A1",
        instructor=_instructor("me@example.test"),
    )


@pytest.fixture
def signed_in(client, course):
    client.post(
        "/api/v1/auth/login/",
        {"email": "me@example.test", "password": PASSWORD},
        content_type="application/json",
    )
    return client


def _count_queries(client, url: str) -> int:
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return len(captured)


def _assert_flat(client, url: str, *, seed, expected: int) -> None:
    """Same endpoint, two dataset sizes, same query count.

    ``seed(n)`` adds n more rows. If the endpoint fans out, the second count
    exceeds the first and the difference names how badly.
    """
    seed(1)
    small = _count_queries(client, url)

    seed(9)
    large = _count_queries(client, url)

    assert small == large, f"{url} fans out: {small} queries for 1 row, {large} for 10"
    assert large == expected, f"{url} now costs {large} queries, expected {expected}"


class TestInstructorLists:
    def test_sections(self, signed_in, course) -> None:
        from apps.catalog.models import Section

        position = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(position)
                Section.objects.create(course=course, title=f"S{index}", position=index)

        # Session, user, the course ownership check, the page itself.
        _assert_flat(
            signed_in,
            f"/api/v1/instructor/courses/{course.id}/sections/",
            seed=seed,
            expected=4,
        )

    def test_lessons(self, signed_in, course) -> None:
        from apps.catalog.models import Lesson, Section

        section = Section.objects.create(course=course, title="Only", position=1)
        position = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(position)
                Lesson.objects.create(
                    course=course,
                    section=section,
                    slug=f"lesson-{index}",
                    title=f"Lesson {index}",
                    position=index,
                )

        _assert_flat(
            signed_in,
            f"/api/v1/instructor/courses/{course.id}/lessons/",
            seed=seed,
            expected=4,
        )

    def test_review_events(self, signed_in, course) -> None:
        """Each row renders the actor's email, which is a join or a query per
        row — the clearest fan-out risk in the instructor API."""
        from apps.catalog.models import CourseReviewEvent

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                # A distinct actor per row: a shared one would be cached by
                # Django's identity map and hide a fan-out.
                CourseReviewEvent.objects.create(
                    course=course,
                    actor=_admin(f"admin-{index}@example.test"),
                    action=CourseReviewEvent.Action.SUBMITTED,
                )

        _assert_flat(
            signed_in,
            f"/api/v1/instructor/courses/{course.id}/review-events/",
            seed=seed,
            expected=4,
        )

    def test_courses(self, signed_in, course) -> None:
        """Already pinned in T4; repeated here so every list endpoint is
        covered in one place and a new one is obviously missing."""
        from apps.catalog.models import Course

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                Course.objects.create(
                    slug=f"extra-{index}",
                    title=f"Extra {index}",
                    language=course.language,
                    level="A1",
                    instructor=_instructor(f"other-{index}@example.test"),
                )

        _assert_flat(signed_in, "/api/v1/instructor/courses/", seed=seed, expected=3)


class TestPublicLists:
    def _publish(self, course) -> None:
        from apps.catalog.services import approve, submit_for_review

        submit_for_review(course=course, by=course.instructor)
        approve(course=course, by=_admin(f"approver-{course.slug}@example.test"))

    def test_catalogue(self, client, course) -> None:
        from apps.catalog.models import Course

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                extra = Course.objects.create(
                    slug=f"extra-{index}",
                    title=f"Extra {index}",
                    language=course.language,
                    level="A1",
                    # A distinct instructor per card, so a missing join shows.
                    instructor=_instructor(f"other-{index}@example.test"),
                )
                self._publish(extra)

        # One. Cursor pagination issues no COUNT, and the view declares no
        # authentication classes, so there is no session or user lookup.
        _assert_flat(client, "/api/v1/catalogue/courses/", seed=seed, expected=1)

    def test_languages(self, client, course) -> None:
        from apps.catalog.models import Course, Language

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                language = Language.objects.create(
                    code=f"l{index}", name=f"Language {index}", native_name=f"L{index}"
                )
                extra = Course.objects.create(
                    slug=f"extra-{index}",
                    title=f"Extra {index}",
                    language=language,
                    level="A1",
                    instructor=_instructor(f"other-{index}@example.test"),
                )
                self._publish(extra)

        _assert_flat(client, "/api/v1/catalogue/languages/", seed=seed, expected=1)
