""" "My courses", and what to play next.

The two questions a returning learner has — *what was I doing* and *where do I
carry on* — answered from one request. Abuse case 4 applies here as it does to
the progress routes: the URL carries no learner, so another learner's list is
unreachable rather than forbidden.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.learning.models import Enrollment, LessonProgress
from apps.learning.selectors import courses_in_progress, next_lesson_for

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db

URL = "/api/v1/me/courses/"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _subscribe(user):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    start_subscription(user=user, provider=FakeBillingProvider())
    return user


def _course(slug: str, *, sections: int = 2, per_section: int = 2):
    """A published course with a real curriculum shape.

    More than one section on purpose: "curriculum order" is section position
    then lesson position, and a single-section fixture cannot tell that apart
    from lesson position alone.
    """
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    instructor = _user(f"teacher-{slug}@example.test", Role.INSTRUCTOR)
    admin = _user(f"approver-{slug}@example.test", Role.ADMIN)
    language, _ = Language.objects.get_or_create(
        code=f"x{slug[:1]}", defaults={"name": slug, "native_name": slug}
    )
    course = Course.objects.create(
        slug=slug, title=slug.title(), language=language, level="A1", instructor=instructor
    )
    lessons = []
    for section_position in range(1, sections + 1):
        section = Section.objects.create(
            course=course, title=f"Part {section_position}", position=section_position
        )
        for lesson_position in range(1, per_section + 1):
            lessons.append(
                Lesson.objects.create(
                    course=course,
                    section=section,
                    slug=f"{slug}-{section_position}-{lesson_position}",
                    title=f"Lesson {section_position}.{lesson_position}",
                    position=lesson_position,
                )
            )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return course, lessons


@pytest.fixture
def learner(db):
    return _subscribe(_user("learner@example.test"))


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _watch(user, lesson, *, completed: bool = False):
    """Progress written through the service, so enrolment happens the way it
    does in production rather than being set up by hand."""
    from apps.learning.services import Heartbeat, mark_complete, record_progress

    record_progress(user=user, lesson=lesson, heartbeat=Heartbeat(15, 15))
    if completed:
        mark_complete(user=user, lesson=lesson)


class TestTheListIsYourOwn:
    def test_it_shows_the_courses_you_have_started(self, client, learner) -> None:
        _, lessons = _course("spanish")
        _watch(learner, lessons[0])
        _sign_in(client, "learner@example.test")

        body = client.get(URL).json()

        assert [row["course_slug"] for row in body["results"]] == ["spanish"]

    def test_and_nobody_else_s(self, client, learner) -> None:
        _, lessons = _course("spanish")
        _, other_lessons = _course("french")
        other = _subscribe(_user("other@example.test"))
        _watch(learner, lessons[0])
        _watch(other, other_lessons[0])

        _sign_in(client, "learner@example.test")
        mine = client.get(URL).json()["results"]
        client.post("/api/v1/auth/logout/")

        _sign_in(client, "other@example.test")
        theirs = client.get(URL).json()["results"]

        # The positive twin matters here: a scope filter matching nothing would
        # satisfy "you cannot see theirs" perfectly.
        assert [row["course_slug"] for row in mine] == ["spanish"]
        assert [row["course_slug"] for row in theirs] == ["french"]

    def test_a_course_never_started_does_not_appear(self, client, learner) -> None:
        _course("spanish")
        _sign_in(client, "learner@example.test")

        assert client.get(URL).json()["results"] == []

    def test_anonymous_is_refused(self, client) -> None:
        assert client.get(URL).status_code in (401, 403)


class TestALapsedSubscriberStillSeesTheirCourses:
    """Deliberate, and the reason this list does not call the resolver.

    An enrolment is a record of what somebody watched, not a grant (ADR-016
    §1). Hiding the list the moment a card fails would lose a learner their own
    history and remove the surface that asks them to come back.
    """

    def test_the_list_survives_an_expired_subscription(self, client, learner) -> None:
        from apps.entitlements.services import expire, live_subscription

        _, lessons = _course("spanish")
        _watch(learner, lessons[0])
        expire(subscription=live_subscription(user=learner))
        _sign_in(client, "learner@example.test")

        body = client.get(URL).json()

        assert [row["course_slug"] for row in body["results"]] == ["spanish"]

    def test_but_the_lesson_behind_it_is_still_gated(self, client, learner) -> None:
        """The twin that stops the above being read as a hole. The list is
        open; playback is not."""
        from apps.entitlements.services import expire, live_subscription

        _, lessons = _course("spanish")
        _watch(learner, lessons[0])
        expire(subscription=live_subscription(user=learner))
        _sign_in(client, "learner@example.test")

        response = client.put(
            f"/api/v1/lessons/{lessons[0].id}/progress/",
            {"position_seconds": 30, "watched_delta_seconds": 15},
            content_type="application/json",
        )

        assert response.status_code == 403


class TestWhatToPlayNext:
    def test_it_is_the_first_lesson_not_yet_completed(self, client, learner) -> None:
        _, lessons = _course("spanish")
        _watch(learner, lessons[0], completed=True)
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["next_lesson"] == str(lessons[1].id)

    def test_curriculum_order_crosses_sections(self, client, learner) -> None:
        """Section position first, then lesson position. A course where the
        second section's lessons restart at position 1 would otherwise send a
        learner backwards."""
        _, lessons = _course("spanish")
        for lesson in lessons[:2]:
            _watch(learner, lesson, completed=True)
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["next_lesson"] == str(lessons[2].id)

    def test_it_walks_back_to_a_skipped_lesson(self, client, learner) -> None:
        """ "Next" is not "after the bookmark". A learner who jumped to the last
        lesson has unfinished ones behind them, and sending them onward would
        quietly write those off."""
        _, lessons = _course("spanish")
        _watch(learner, lessons[3], completed=True)
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["last_lesson"] == str(lessons[3].id)
        assert row["next_lesson"] == str(lessons[0].id)

    def test_it_is_null_when_the_course_is_finished(self, client, learner) -> None:
        _, lessons = _course("spanish")
        for lesson in lessons:
            _watch(learner, lesson, completed=True)
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["next_lesson"] is None

    def test_another_learner_s_completions_do_not_move_your_next_lesson(
        self, client, learner
    ) -> None:
        """The subquery filters on the requesting user. Without that, one
        learner finishing a course would advance everybody in it."""
        _, lessons = _course("spanish")
        other = _subscribe(_user("other@example.test"))
        for lesson in lessons:
            _watch(other, lesson, completed=True)
        _watch(learner, lessons[0])
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["next_lesson"] == str(lessons[0].id)

    def test_the_selector_says_none_when_nothing_is_left(self, learner) -> None:
        course, lessons = _course("spanish")
        for lesson in lessons:
            _watch(learner, lesson, completed=True)

        assert next_lesson_for(user=learner, course=course) is None

    def test_and_names_the_lesson_otherwise(self, learner) -> None:
        course, lessons = _course("spanish")

        assert next_lesson_for(user=learner, course=course) == lessons[0]


class TestCounts:
    def test_counts_survive_the_join(self, client, learner) -> None:
        """The `distinct=True` trap, provoked.

        The filtered count joins through progress on *every* learner's rows,
        which multiplies what the unfiltered count sees. One learner alone does
        not provoke it — there is one progress row per lesson, so the join is
        one-to-one and a non-distinct count is accidentally right. A second
        learner watching the same course is what makes `lesson_count` report
        eight lessons in a course that has four.
        """
        _, lessons = _course("spanish")
        classmate = _subscribe(_user("classmate@example.test"))
        for lesson in lessons:
            _watch(classmate, lesson, completed=True)
        for lesson in lessons[:3]:
            _watch(learner, lesson, completed=True)
        _watch(learner, lessons[3])
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["lesson_count"] == 4
        assert row["completed_lesson_count"] == 3

    def test_completions_are_counted_per_learner(self, client, learner) -> None:
        _, lessons = _course("spanish")
        other = _subscribe(_user("other@example.test"))
        for lesson in lessons:
            _watch(other, lesson, completed=True)
        _watch(learner, lessons[0], completed=True)
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["completed_lesson_count"] == 1

    def test_a_started_but_unfinished_course_counts_zero(self, client, learner) -> None:
        _, lessons = _course("spanish")
        _watch(learner, lessons[0])
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["completed_lesson_count"] == 0
        assert row["lesson_count"] == 4

    def test_last_activity_is_reported(self, client, learner) -> None:
        _, lessons = _course("spanish")
        _watch(learner, lessons[0])
        _sign_in(client, "learner@example.test")

        row = client.get(URL).json()["results"][0]

        assert row["last_activity"] is not None


class TestQueryCost:
    def test_my_courses_costs_the_same_for_one_course_or_ten(
        self, client, learner, django_assert_num_queries
    ) -> None:
        """ADR-009: the counts and "what next" are annotations precisely so
        that this list does not grow a query per course.

        Ten courses rather than two, because an N+1 with a small fixture hides
        inside the fixed cost.
        """
        for index in range(10):
            _, lessons = _course(f"course{index}")
            _watch(learner, lessons[0], completed=True)
        _sign_in(client, "learner@example.test")

        # Warm any lazily-populated request state so the measurement is of the
        # list, not of the first request in the process.
        client.get(URL)

        with django_assert_num_queries(3):
            body = client.get(URL).json()

        # Session, user, the annotated list. The assertion above is worthless
        # without this: an empty page costs three queries too.
        assert len(body["results"]) == 10
        assert all(row["completed_lesson_count"] == 1 for row in body["results"])


class TestTheSelectorIsScoped:
    def test_it_never_returns_another_learner_s_enrolment(self, learner) -> None:
        _, lessons = _course("spanish")
        other = _subscribe(_user("other@example.test"))
        _watch(other, lessons[0])
        _watch(learner, lessons[1])

        rows = list(courses_in_progress(user=learner))

        assert len(rows) == 1
        assert rows[0].user_id == learner.pk
        assert Enrollment.objects.count() == 2
        assert LessonProgress.objects.count() == 2
