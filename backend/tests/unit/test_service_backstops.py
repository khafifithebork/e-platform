"""The guards that only a non-API caller can reach.

T2 measured §8.1 and found every target met. What it also found was three
uncovered spots sharing one shape, and that shape is the point of this file:
**a check written as a backstop, tested only through the path that makes it
unreachable.**

`grant_access_override` refuses a bad duration and a blank reason. There are
tests for both refusals — and both go through the API, where the serializer
rejects first, so the service's own checks never execute. The docstring says
they exist "because the service is reachable from a management command where no
serializer runs". Nothing was calling it that way.

That is not a coverage statistic. It is a control that would have been deleted
in a refactor with a green suite, and the deletion would only surface the first
time somebody granted an override from a shell.
"""

from __future__ import annotations

import pytest

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, *, role=None):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    if role:
        user.role = role
        user.save(update_fields=["role"])
    return user


class TestTheOverrideGuardsWithoutASerializer:
    """Called directly, the way a management command would."""

    def test_a_duration_below_one_day_is_refused(self, settings) -> None:
        from apps.accounts.models import Role
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(actor=admin, user=learner, days=0, reason="Because")

    def test_a_duration_above_the_maximum_is_refused(self, settings) -> None:
        from apps.accounts.models import Role
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(
                actor=admin,
                user=learner,
                days=settings.ACCESS_OVERRIDE_MAX_DAYS + 1,
                reason="Because",
            )

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
    def test_a_blank_reason_is_refused(self, reason: str) -> None:
        from apps.accounts.models import Role
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(actor=admin, user=learner, days=7, reason=reason)

    def test_and_nothing_is_written_when_it_refuses(self) -> None:
        """The twin. A guard that raised *after* creating the row would satisfy
        every test above and still leave an unexplained override behind."""
        from apps.accounts.models import Role
        from apps.core.models import AuditLog
        from apps.entitlements.models import AccessOverride
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(actor=admin, user=learner, days=7, reason="  ")

        assert not AccessOverride.objects.exists()
        assert not AuditLog.objects.exists()

    def test_but_a_valid_grant_still_works(self) -> None:
        """The positive twin. A service that refused everything would pass all
        four assertions above."""
        from apps.accounts.models import Role
        from apps.entitlements.models import AccessOverride
        from apps.entitlements.services import grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        grant_access_override(actor=admin, user=learner, days=7, reason="Double charged")

        assert AccessOverride.objects.count() == 1


class TestATrialSurvivesATransition:
    """`trial_end` is not lost when a trialing subscription moves on.

    **This does not cover `_apply`'s carry-forward branch, and the first
    version of this docstring said it did.** Measured afterwards: the line
    stayed uncovered. `trial_end` survives a renewal because `_apply` leaves
    the field alone when the provider's snapshot carries no trial end — not
    because the assignment ran.

    The branch needs a snapshot *with* a `trial_end` arriving through `_apply`,
    and `FakeBillingProvider.renew_subscription` never sets one. It is
    unreachable through the only provider that exists, and reaching it would
    mean teaching the fake to report something no real provider has been
    observed doing — §6's invention, in test clothing. **M8 covers it**, with a
    provider whose renewal payload is a fact rather than a guess.

    The behaviour below is still worth pinning: a renewal that cleared the
    column would fail it, and that is the failure support would feel.
    """

    def test_the_trial_end_is_kept_after_the_trial_converts(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        from apps.entitlements.models import Subscription

        learner = _user("learner@example.test")
        call_command("billing", "start", email=learner.email, trial_days=14, stdout=StringIO())

        subscription = Subscription.objects.get(user=learner)
        assert subscription.trial_end is not None
        started_with = subscription.trial_end

        call_command("billing", "renew", email=learner.email, stdout=StringIO())

        subscription.refresh_from_db()
        assert subscription.trial_end == started_with, "the trial end was cleared or moved"

    def test_and_the_status_actually_moved(self) -> None:
        """The twin. A renewal that silently did nothing would preserve
        `trial_end` perfectly."""
        from io import StringIO

        from django.core.management import call_command

        from apps.entitlements.models import Subscription

        learner = _user("learner@example.test")
        call_command("billing", "start", email=learner.email, trial_days=14, stdout=StringIO())
        call_command("billing", "renew", email=learner.email, stdout=StringIO())

        assert Subscription.objects.get(user=learner).status == "ACTIVE"


class TestTheLockoutReadsAFormLogin:
    """django-axes attributes a failed attempt to a username.

    `accounts/axes.py` reads `credentials` first and falls back to the posted
    form field, and the fallback exists for one reason: **Django Admin posts a
    form**, not JSON. Every test in the suite posts JSON, so the fallback — the
    half that protects the highest-value login in the system — was the
    uncovered line.
    """

    def test_a_form_post_is_attributed(self, rf) -> None:
        from apps.accounts.axes import get_username

        request = rf.post("/login/", {"email": "learner@example.test"})

        assert get_username(request, credentials=None) == "learner@example.test"

    def test_credentials_win_when_both_are_present(self, rf) -> None:
        """The authoritative source is what was passed to `authenticate()`, not
        a re-read of a body a middleware may have altered."""
        from apps.accounts.axes import get_username

        request = rf.post("/login/", {"email": "from-the-form@example.test"})

        username = get_username(request, credentials={"email": "from-credentials@example.test"})

        assert username == "from-credentials@example.test"

    def test_empty_credentials_fall_through_to_the_form(self, rf) -> None:
        """The partial branch: `credentials` is present but carries nothing
        usable. Falling through matters because django-axes would otherwise key
        the lockout on an empty username for a request that named one."""
        from apps.accounts.axes import get_username

        request = rf.post("/login/", {"email": "learner@example.test"})

        assert get_username(request, credentials={"email": ""}) == "learner@example.test"

    def test_neither_present_is_an_empty_string_rather_than_none(self, rf) -> None:
        """django-axes keys its lockout on this value. `None` and `""` are
        different keys, and a lockout keyed on `None` is a lockout shared by
        every anonymous failure."""
        from apps.accounts.axes import get_username

        assert get_username(rf.post("/login/", {}), credentials=None) == ""


class TestCourseContentWrites:
    @pytest.fixture
    def course(self):
        from apps.accounts.models import Role
        from apps.catalog.models import Course, Language

        return Course.objects.create(
            slug="service-course",
            title="Original title",
            description="Original description",
            skill_areas=["listening"],
            language=Language.objects.create(code="es", name="Spanish"),
            level="A1",
            instructor=_user("owner@example.test", role=Role.INSTRUCTOR),
        )

    def test_another_instructor_cannot_edit_through_the_service(self, course) -> None:
        from apps.accounts.models import Role
        from apps.catalog.services import NotPermitted, update_course

        other = _user("other@example.test", role=Role.INSTRUCTOR)
        with pytest.raises(NotPermitted):
            update_course(course=course, by=other, title="Hijacked")

        course.refresh_from_db()
        assert course.title == "Original title"
        assert course.instructor_id != other.pk

    def test_explicit_empty_fields_are_saved_and_omitted_fields_survive(self, course) -> None:
        from apps.catalog.services import update_course

        updated = update_course(course=course, by=course.instructor, description="", skill_areas=[])

        updated.refresh_from_db()
        assert updated.description == ""
        assert updated.skill_areas == []
        assert updated.title == "Original title"
        assert updated.level == "A1"
        assert updated.search_vector is not None

    def test_service_creation_retains_defaults_and_indexes_content(self, course) -> None:
        from apps.catalog.models import CourseStatus
        from apps.catalog.services import create_course

        created = create_course(
            instructor=course.instructor,
            slug="created-by-service",
            title="New course",
            language=course.language,
            level="A2",
        )

        created.refresh_from_db()
        assert created.instructor_id == course.instructor_id
        assert created.status == CourseStatus.DRAFT
        assert created.published_at is None
        assert created.description == ""
        assert created.skill_areas == []
        assert created.search_vector is not None


class TestSectionWrites:
    @pytest.fixture
    def courses(self):
        from apps.accounts.models import Role
        from apps.catalog.models import Course, Language

        owner = _user("section-owner@example.test", role=Role.INSTRUCTOR)
        language = Language.objects.create(code="es", name="Spanish")
        return [
            Course.objects.create(
                slug=slug, title=slug, language=language, level="A1", instructor=owner
            )
            for slug in ("first-course", "second-course")
        ]

    def test_creation_records_the_supplied_course(self, courses) -> None:
        from apps.catalog.services import create_section

        course = courses[0]
        section = create_section(course=course, by=course.instructor, title="First", position=1)

        section.refresh_from_db()
        assert section.course_id == course.pk
        assert section.title == "First"
        assert section.position == 1

    def test_another_instructor_cannot_create_or_edit_sections(self, courses) -> None:
        from apps.accounts.models import Role
        from apps.catalog.models import Section
        from apps.catalog.services import NotPermitted, create_section, update_section

        course = courses[0]
        other = _user("section-other@example.test", role=Role.INSTRUCTOR)
        with pytest.raises(NotPermitted):
            create_section(course=course, by=other, title="Injected", position=1)
        assert not Section.objects.filter(course=course).exists()

        section = Section.objects.create(course=course, title="Original", position=1)
        with pytest.raises(NotPermitted):
            update_section(section=section, course=course, by=other, title="Hijacked")
        section.refresh_from_db()
        assert section.title == "Original"

    def test_a_section_cannot_be_edited_through_another_owned_course(self, courses) -> None:
        from apps.catalog.models import Section
        from apps.catalog.services import NotPermitted, update_section

        first, second = courses
        section = Section.objects.create(course=first, title="Original", position=1)
        with pytest.raises(NotPermitted):
            update_section(
                section=section, course=second, by=second.instructor, title="Wrong parent"
            )
        section.refresh_from_db()
        assert section.title == "Original"
        assert section.course_id == first.pk

    def test_partial_edits_preserve_omitted_fields(self, courses) -> None:
        from apps.catalog.models import Section
        from apps.catalog.services import update_section

        course = courses[0]
        section = Section.objects.create(course=course, title="Original", position=1)
        updated = update_section(section=section, course=course, by=course.instructor, position=0)
        updated.refresh_from_db()
        assert updated.position == 0
        assert updated.title == "Original"

    @pytest.mark.django_db(transaction=True)
    def test_position_conflicts_roll_back_the_edit(self, courses) -> None:
        from django.db import IntegrityError

        from apps.catalog.models import Section
        from apps.catalog.services import update_section

        course = courses[0]
        Section.objects.create(course=course, title="First", position=1)
        second = Section.objects.create(course=course, title="Second", position=2)
        with pytest.raises(IntegrityError):
            update_section(
                section=second, course=course, by=course.instructor, title="Conflicting", position=1
            )
        second.refresh_from_db()
        assert second.title == "Second"
        assert second.position == 2


class TestLessonWrites:
    @pytest.fixture
    def lesson_context(self):
        from types import SimpleNamespace

        from apps.accounts.models import Role
        from apps.catalog.models import Course, Language, Lesson, Section

        owner = _user("lesson-owner@example.test", role=Role.INSTRUCTOR)
        language = Language.objects.create(code="es", name="Spanish")
        course, other_course = [
            Course.objects.create(
                slug=slug, title=slug, language=language, level="A1", instructor=owner
            )
            for slug in ("lesson-course", "other-course")
        ]
        section = Section.objects.create(course=course, title="First", position=1)
        foreign = Section.objects.create(course=other_course, title="Foreign", position=1)
        lesson = Lesson.objects.create(
            course=course,
            section=section,
            slug="intro",
            title="Original",
            body="Original body",
            position=1,
            is_preview=True,
        )
        return SimpleNamespace(
            course=course,
            other_course=other_course,
            section=section,
            foreign=foreign,
            lesson=lesson,
        )

    def test_service_creation_defaults_to_a_non_preview_lesson(self, lesson_context) -> None:
        from apps.catalog.services import create_lesson

        c = lesson_context
        created = create_lesson(
            course=c.course,
            section=c.section,
            by=c.course.instructor,
            slug="created",
            title="Created",
            position=2,
        )
        created.refresh_from_db()
        assert created.course_id == c.course.pk
        assert created.section_id == c.section.pk
        assert created.body == ""
        assert created.lesson_type == "VIDEO"
        assert created.is_preview is False

    def test_creation_rejects_another_owned_courses_section(self, lesson_context) -> None:
        from apps.catalog.models import Lesson
        from apps.catalog.services import NotPermitted, create_lesson

        c = lesson_context
        with pytest.raises(NotPermitted):
            create_lesson(
                course=c.course,
                section=c.foreign,
                by=c.course.instructor,
                slug="injected",
                title="Injected",
                position=2,
            )
        assert not Lesson.objects.filter(slug="injected").exists()

    def test_another_instructor_cannot_create_or_edit(self, lesson_context) -> None:
        from apps.accounts.models import Role
        from apps.catalog.models import Lesson
        from apps.catalog.services import NotPermitted, create_lesson, update_lesson

        c = lesson_context
        other = _user("lesson-other@example.test", role=Role.INSTRUCTOR)
        with pytest.raises(NotPermitted):
            create_lesson(
                course=c.course,
                section=c.section,
                by=other,
                slug="injected",
                title="Injected",
                position=2,
            )
        assert not Lesson.objects.filter(slug="injected").exists()
        with pytest.raises(NotPermitted):
            update_lesson(lesson=c.lesson, course=c.course, by=other, title="Hijacked")
        c.lesson.refresh_from_db()
        assert c.lesson.title == "Original"

    def test_edit_rejects_another_owned_course_as_context(self, lesson_context) -> None:
        from apps.catalog.services import NotPermitted, update_lesson

        c = lesson_context
        with pytest.raises(NotPermitted):
            update_lesson(
                lesson=c.lesson,
                course=c.other_course,
                by=c.course.instructor,
                title="Wrong context",
            )
        c.lesson.refresh_from_db()
        assert c.lesson.title == "Original"
        assert c.lesson.course_id == c.course.pk

    def test_edit_rejects_a_section_from_another_owned_course(self, lesson_context) -> None:
        from apps.catalog.services import NotPermitted, update_lesson

        c = lesson_context
        with pytest.raises(NotPermitted):
            update_lesson(
                lesson=c.lesson,
                course=c.course,
                by=c.course.instructor,
                section=c.foreign,
                title="Wrong section",
            )
        c.lesson.refresh_from_db()
        assert c.lesson.section_id == c.section.pk
        assert c.lesson.title == "Original"

    def test_partial_edit_preserves_omitted_fields_and_preview(self, lesson_context) -> None:
        from apps.catalog.services import update_lesson

        c = lesson_context
        updated = update_lesson(
            lesson=c.lesson, course=c.course, by=c.course.instructor, body="", position=0
        )
        updated.refresh_from_db()
        assert updated.body == ""
        assert updated.position == 0
        assert updated.title == "Original"
        assert updated.slug == "intro"
        assert updated.section_id == c.section.pk
        assert updated.is_preview is True

    @pytest.mark.django_db(transaction=True)
    def test_position_conflict_rolls_back_the_edit(self, lesson_context) -> None:
        from django.db import IntegrityError

        from apps.catalog.models import Lesson
        from apps.catalog.services import update_lesson

        c = lesson_context
        second = Lesson.objects.create(
            course=c.course, section=c.section, slug="second", title="Second", position=2
        )
        with pytest.raises(IntegrityError):
            update_lesson(
                lesson=second,
                course=c.course,
                by=c.course.instructor,
                title="Conflicting",
                position=1,
            )
        second.refresh_from_db()
        assert second.title == "Second"
        assert second.position == 2
