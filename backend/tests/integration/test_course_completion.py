"""Finishing a course.

The last question in the milestone's objective sentence — *watch → progress
persists → resume across devices → course completes*.

The decision worth reading here is what happens **after** somebody finishes. A
completion date is never cleared and never recomputed, so a course that gains a
lesson afterwards leaves its finishers finished. That produces a course showing
four of five lessons complete beside a completion date, which looks like a bug
until you know it was chosen: they finished the course as it stood, and taking
that back is not something progress recording should be able to do.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.learning.models import Enrollment
from apps.learning.services import course_is_complete

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


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


def _course(slug: str = "spanish", *, lessons: int = 3):
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
    section = Section.objects.create(course=course, title="Part 1", position=1)
    made = [
        Lesson.objects.create(
            course=course,
            section=section,
            slug=f"{slug}-{position}",
            title=f"Lesson {position}",
            position=position,
        )
        for position in range(1, lessons + 1)
    ]
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return course, section, made


@pytest.fixture
def learner(db):
    return _subscribe(_user("learner@example.test"))


def _finish(user, lesson):
    from apps.learning.services import mark_complete

    return mark_complete(user=user, lesson=lesson)


def _watch(user, lesson, *, seconds: int = 15):
    from apps.learning.services import Heartbeat, record_progress

    return record_progress(user=user, lesson=lesson, heartbeat=Heartbeat(seconds, seconds))


class TestFinishingACourse:
    def test_completing_every_lesson_completes_the_course(self, learner) -> None:
        _, _, lessons = _course()

        for lesson in lessons:
            _finish(learner, lesson)

        assert Enrollment.objects.get(user=learner).completed_at is not None

    def test_one_lesson_short_is_not_finished(self, learner) -> None:
        """The twin. Without it, a rule that completed on any lesson would
        satisfy the test above perfectly."""
        _, _, lessons = _course()

        for lesson in lessons[:-1]:
            _finish(learner, lesson)

        assert Enrollment.objects.get(user=learner).completed_at is None

    def test_the_date_does_not_move_when_a_lesson_is_re_marked(self, learner) -> None:
        """When somebody finished is the one thing the field is for."""
        _, _, lessons = _course()
        for lesson in lessons:
            _finish(learner, lesson)
        first = Enrollment.objects.get(user=learner).completed_at

        _finish(learner, lessons[0])

        assert Enrollment.objects.get(user=learner).completed_at == first

    def test_nor_when_the_learner_rewatches(self, learner) -> None:
        _, _, lessons = _course()
        for lesson in lessons:
            _finish(learner, lesson)
        first = Enrollment.objects.get(user=learner).completed_at

        _watch(learner, lessons[0], seconds=5)

        assert Enrollment.objects.get(user=learner).completed_at == first

    def test_completion_by_watched_time_also_finishes_the_course(self, learner, settings) -> None:
        """The other route into completion. A course that could only be
        finished by pressing a button would never complete for the learner who
        simply watches it."""
        from apps.media_assets.models import MediaAsset, MediaAssetStatus

        _, _, lessons = _course(lessons=1)
        MediaAsset.objects.create(
            lesson=lessons[0],
            source_object_key="masters/abc/def.mp4",
            source_bytes=2048,
            provider="fake",
            provider_asset_id="fakeasset_abc",
            provider_playback_id="fakeplay_abc",
            status=MediaAssetStatus.READY,
            duration_seconds=20,
        )

        _watch(learner, lessons[0], seconds=20)

        assert Enrollment.objects.get(user=learner).completed_at is not None


class TestWhatCannotCompleteACourse:
    def test_an_empty_course_never_completes(self, learner) -> None:
        """Zero of zero is "all of them" to a naive comparison, and an empty
        course would complete the instant anybody touched it."""
        course, _, _ = _course(lessons=1)
        from apps.catalog.models import Lesson

        assert not course_is_complete(user=learner, course_id=course.pk)

        Lesson.objects.filter(course=course).delete()

        assert not course_is_complete(user=learner, course_id=course.pk)

    def test_another_learner_s_completions_do_not_finish_your_course(self, learner) -> None:
        """The learner has to *finish a lesson* for this to prove anything.

        An ordinary heartbeat never reaches the rule — no duration, so no
        completion, so no check — and the first version of this test passed
        with the user filter removed entirely.
        """
        _, _, lessons = _course()
        classmate = _subscribe(_user("classmate@example.test"))
        for lesson in lessons:
            _finish(classmate, lesson)

        _finish(learner, lessons[0])

        assert Enrollment.objects.get(user=learner).completed_at is None
        assert Enrollment.objects.get(user=classmate).completed_at is not None

    def test_finishing_one_course_does_not_finish_another(self, learner) -> None:
        """Same shape, one level out: the learner needs completions in the
        other course *and* a completion here, or an unscoped count has nothing
        to over-count."""
        _, _, spanish = _course("spanish")
        _, _, french = _course("french")
        for lesson in spanish:
            _finish(learner, lesson)

        _finish(learner, french[0])

        assert Enrollment.objects.get(user=learner, course__slug="spanish").completed_at is not None
        assert Enrollment.objects.get(user=learner, course__slug="french").completed_at is None


class TestACompletedCourseStaysCompleted:
    """The decision. A completion date is set once and never recomputed."""

    def test_a_new_lesson_does_not_un_finish_the_course(self, learner) -> None:
        from apps.catalog.models import Lesson

        course, section, lessons = _course()
        for lesson in lessons:
            _finish(learner, lesson)
        finished_at = Enrollment.objects.get(user=learner).completed_at

        added = Lesson.objects.create(
            course=course, section=section, slug="new", title="New", position=99
        )
        _watch(learner, added)

        assert Enrollment.objects.get(user=learner).completed_at == finished_at

    def test_and_the_counts_say_what_is_actually_true(self, client, learner) -> None:
        """The visible consequence, asserted rather than hidden: the counter
        reports three of four while the completion date stands. Somebody
        reading this later should find the inconsistency deliberate."""
        from apps.catalog.models import Lesson

        course, section, lessons = _course()
        for lesson in lessons:
            _finish(learner, lesson)
        Lesson.objects.create(course=course, section=section, slug="new", title="New", position=99)

        client.post(
            "/api/v1/auth/login/",
            {"email": "learner@example.test", "password": PASSWORD},
            content_type="application/json",
        )
        row = client.get("/api/v1/me/courses/").json()["results"][0]

        assert row["completed_lesson_count"] == 3
        assert row["lesson_count"] == 4
        assert row["completed_at"] is not None
        assert row["next_lesson"] is not None


class TestTheCheckIsRare:
    def test_an_ordinary_heartbeat_does_not_count_lessons(self, learner) -> None:
        """The rule runs only on the transition that can change its answer.
        On the highest-frequency write in the product, re-answering a question
        whose inputs have not moved costs two queries per beat.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _, _, lessons = _course()
        _watch(learner, lessons[0])

        with CaptureQueriesContext(connection) as captured:
            _watch(learner, lessons[0], seconds=30)

        counting = [
            query
            for query in captured.captured_queries
            if "COUNT(" in query["sql"].upper() and "catalog_lesson" in query["sql"]
        ]

        assert counting == []

    def test_but_it_does_run_when_a_lesson_completes(self, learner) -> None:
        """The positive twin: a check that never ran would pass the test above
        and never complete a course."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _, _, lessons = _course()
        _watch(learner, lessons[0])

        with CaptureQueriesContext(connection) as captured:
            _finish(learner, lessons[0])

        counting = [
            query
            for query in captured.captured_queries
            if "COUNT(" in query["sql"].upper() and "catalog_lesson" in query["sql"]
        ]

        assert counting != []


class TestTheRuleLivesInOnePlace:
    def test_nothing_outside_the_service_writes_a_course_completion_date(self) -> None:
        """§10 M7 and ADR-016 §2: a second definition of "finished" is the trap
        this milestone is most likely to fall into, and it would arrive as a
        serializer or a view setting the date itself.
        """
        import ast
        from pathlib import Path

        apps_root = Path(__file__).resolve().parents[2] / "apps"
        allowed = apps_root / "learning" / "services.py"
        offenders = []

        for path in apps_root.rglob("*.py"):
            if "migrations" in path.parts or path == allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "completed_at"
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "enrollment"
                    ):
                        offenders.append(f"{path.relative_to(apps_root)}:{node.lineno}")

        assert not offenders, (
            f"Course completion is defined in learning/services.py and nowhere else. {offenders}"
        )

    def test_the_guard_recognises_what_it_looks_for(self) -> None:
        """ADR-006: a structural guard nobody has seen fire is not a guard."""
        import ast

        offending = ast.parse("enrollment.completed_at = timezone.now()\n")

        found = [
            node
            for node in ast.walk(offending)
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "completed_at"
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == "enrollment"
        ]

        assert found
