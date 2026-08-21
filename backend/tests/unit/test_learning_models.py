"""Enrolment and progress, and the constraints that hold them true.

Invariant 11: every test writes a row a constraint must reject and asserts
PostgreSQL refuses it, matched by constraint **name** — a bare
``IntegrityError`` would pass when some other constraint did the refusing.

Two of these carry more weight than the rest.

The uniqueness of ``(user, lesson)`` is **correctness, not speed** (§5.3). A
progress heartbeat is a write every fifteen seconds from a client that may
retry, so without it a lesson accumulates a row per beat and "where did I get
to" has hundreds of answers.

And ``max_position_seconds >= last_position_seconds`` encodes something the
column names only imply: the furthest point reached cannot be behind the
current one. Without it, rewatching from the start would quietly rewrite how
far somebody had got.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def course(db):
    from apps.catalog.models import Course, Language

    instructor = _user("teacher@example.test", Role.INSTRUCTOR)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    return Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )


@pytest.fixture
def lesson(db, course):
    from apps.catalog.models import Lesson, Section

    section = Section.objects.create(course=course, title="Greetings", position=1)
    return Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )


@pytest.fixture
def learner(db):
    return _user("learner@example.test")


def _enrol(user, course, **overrides):
    from apps.learning.models import Enrollment

    return Enrollment.objects.create(**{"user": user, "course": course, **overrides})


def _progress(user, lesson, **overrides):
    from apps.learning.models import LessonProgress

    fields = {
        "user": user,
        "lesson": lesson,
        "last_position_seconds": 30,
        "max_position_seconds": 30,
        "watched_seconds": 30,
    }
    return LessonProgress.objects.create(**{**fields, **overrides})


class TestOneEnrolmentPerCourse:
    def test_a_second_enrolment_is_refused(self, learner, course) -> None:
        """Two enrolments are two sets of progress for one course, and
        "resume" would have to pick."""
        _enrol(learner, course)

        with pytest.raises(IntegrityError, match="one_enrollment_per_course"):
            _enrol(learner, course)

    def test_two_learners_may_take_the_same_course(self, learner, course) -> None:
        other = _user("other@example.test")

        _enrol(learner, course)
        _enrol(other, course)

    def test_one_learner_may_take_two_courses(self, learner, course) -> None:
        from apps.catalog.models import Course

        second = Course.objects.create(
            slug="french",
            title="French",
            language=course.language,
            level="A1",
            instructor=course.instructor,
        )

        _enrol(learner, course)
        _enrol(learner, second)


class TestOneProgressRowPerLesson:
    """§5.3 calls this correctness rather than speed, and it is."""

    def test_a_second_row_is_refused(self, learner, lesson) -> None:
        """A heartbeat every fifteen seconds from a retrying client is what
        this prevents: without it, an hour of watching is two hundred and
        forty rows and "where did I get to" has no single answer."""
        _progress(learner, lesson)

        with pytest.raises(IntegrityError, match="one_progress_row_per_lesson"):
            _progress(learner, lesson)

    def test_two_learners_progress_independently(self, learner, lesson) -> None:
        other = _user("other@example.test")

        _progress(learner, lesson)
        _progress(other, lesson)


class TestProgressOccupiesRealTime:
    def test_a_negative_position_is_refused(self, learner, lesson) -> None:
        """Refused by the check `PositiveIntegerField` emits for itself.

        Written first against an explicit constraint of our own, which never
        fired: Django's is created first and refuses the row before ours is
        reached. Two constraints where one can never be the one that refuses
        is dead weight reading as protection, so ours was removed and this
        matches the field name in the check that actually does the work.
        """
        with pytest.raises(IntegrityError, match="last_position_seconds_check"):
            _progress(learner, lesson, last_position_seconds=-1, max_position_seconds=0)

    def test_negative_watched_time_is_refused(self, learner, lesson) -> None:
        with pytest.raises(IntegrityError, match="watched_seconds_check"):
            _progress(learner, lesson, watched_seconds=-1)

    def test_the_furthest_point_cannot_be_behind_the_current_one(self, learner, lesson) -> None:
        """Encodes what the column names only imply. Without it, rewatching
        from the start would quietly rewrite how far somebody had got."""
        with pytest.raises(IntegrityError, match="max_position_is_at_least_last"):
            _progress(learner, lesson, last_position_seconds=100, max_position_seconds=50)

    def test_the_two_may_be_equal(self, learner, lesson) -> None:
        """The ordinary case: watching forwards, never having rewound."""
        _progress(learner, lesson, last_position_seconds=100, max_position_seconds=100)

    def test_rewinding_is_allowed(self, learner, lesson) -> None:
        """The positive twin. A constraint requiring strict inequality would
        satisfy the test above and make it impossible to rewind."""
        _progress(learner, lesson, last_position_seconds=20, max_position_seconds=100)


class TestBookmarks:
    def test_an_enrolment_remembers_the_last_lesson(self, learner, course, lesson) -> None:
        enrollment = _enrol(learner, course, last_lesson=lesson)

        assert enrollment.last_lesson == lesson

    def test_deleting_that_lesson_does_not_delete_the_enrolment(
        self, learner, course, lesson
    ) -> None:
        """A bookmark pointing at a removed lesson is meaningless; the
        progress and the enrolment behind it are not. SET_NULL rather than
        CASCADE, which would take somebody's whole course history with one
        deleted lesson."""
        from apps.learning.models import Enrollment

        enrollment = _enrol(learner, course, last_lesson=lesson)
        lesson.delete()

        enrollment.refresh_from_db()
        assert enrollment.last_lesson is None
        assert Enrollment.objects.filter(pk=enrollment.pk).exists()

    def test_an_enrolment_starts_incomplete(self, learner, course) -> None:
        assert _enrol(learner, course).completed_at is None


class TestEnrolmentIsNotEntitlement:
    """ADR-016 §1, guarded structurally.

    The wrong answer here is tempting — "you must be enrolled to watch" reads
    like an ordinary product rule — and behavioural tests for it live in T9,
    where there is a stack to run them against. This is the cheaper guard: the
    resolver cannot consult a model it does not import, so a second
    entitlement rule cannot be written there by accident.
    """

    def test_the_entitlements_app_does_not_know_enrolment_exists(self) -> None:
        import ast
        from pathlib import Path

        entitlements = Path(__file__).resolve().parents[2] / "apps" / "entitlements"
        offenders = []

        for path in entitlements.rglob("*.py"):
            if "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and "learning" in node.module:
                    offenders.append(f"{path.name}: {node.module}")

        assert not offenders, (
            "Entitlement must not depend on enrolment (ADR-016 §1): access and "
            f"progress are different questions. {offenders}"
        )

    def test_the_guard_recognises_what_it_looks_for(self) -> None:
        """ADR-006: a structural guard nobody has seen fire is not a guard."""
        import ast

        offending = ast.parse("from apps.learning.models import Enrollment\n")

        found = [
            node
            for node in ast.walk(offending)
            if isinstance(node, ast.ImportFrom) and node.module and "learning" in node.module
        ]

        assert found
