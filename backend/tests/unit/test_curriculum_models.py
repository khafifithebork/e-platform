"""Sections and lessons.

The constraints are the content of this task. ADR-007 §1 chose a redundant
`course` foreign key on `Lesson` specifically so that "a lesson slug is unique
within its course" is a database guarantee rather than a service convention —
and a guarantee is only worth the redundancy if something proves the database
actually refuses.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction


@pytest.fixture
def course(db):
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, Language

    instructor = create_account(email="teacher@example.test", password="a-long-enough-passphrase")
    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    return Course.objects.create(
        slug="spanish-for-beginners",
        title="Spanish for beginners",
        language=language,
        level="A1",
        instructor=instructor,
    )


@pytest.fixture
def section(course):
    from apps.catalog.models import Section

    return Section.objects.create(course=course, title="Greetings", position=1)


def _lesson(course, section, **overrides):
    from apps.catalog.models import Lesson

    return Lesson.objects.create(
        **{
            "course": course,
            "section": section,
            "slug": "introduction",
            "title": "Introduction",
            "position": 1,
            **overrides,
        }
    )


@pytest.mark.django_db
class TestSectionOrdering:
    def test_two_sections_cannot_share_a_position(self, course, section) -> None:
        """The constraint is DEFERRED, which makes it awkward to provoke.

        Deferred constraints are checked at the outermost commit — and inside
        pytest-django every test runs in a transaction that is rolled back, so
        that commit never happens and the violation never surfaces. Forcing
        IMMEDIATE is what makes this a real assertion rather than a test that
        passes because nothing was ever checked.
        """
        from django.db import connection

        from apps.catalog.models import Section

        with pytest.raises(IntegrityError), transaction.atomic():
            connection.cursor().execute("SET CONSTRAINTS ALL IMMEDIATE")
            Section.objects.create(course=course, title="Numbers", position=1)

    def test_positions_are_per_course_not_global(self, course, section) -> None:
        """Another course starting at position 1 is normal, not a collision."""
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Section

        other = Course.objects.create(
            slug="french-for-beginners",
            title="French",
            language=course.language,
            level="A1",
            instructor=create_account(
                email="other@example.test", password="a-long-enough-passphrase"
            ),
        )

        assert Section.objects.create(course=other, title="Salutations", position=1)

    def test_swapping_two_positions_in_one_transaction_is_allowed(self, course, section) -> None:
        """The reason the constraint is DEFERRED.

        Reordering necessarily passes through a state where two rows share a
        position. An immediate constraint rejects that mid-statement and makes
        reordering impossible without a temporary sentinel value.
        """
        from django.db import connection

        from apps.catalog.models import Section

        second = Section.objects.create(course=course, title="Numbers", position=2)

        with transaction.atomic():
            connection.cursor().execute("SET CONSTRAINTS ALL DEFERRED")
            Section.objects.filter(pk=section.pk).update(position=2)
            Section.objects.filter(pk=second.pk).update(position=1)

        section.refresh_from_db()
        second.refresh_from_db()
        assert (section.position, second.position) == (2, 1)


@pytest.mark.django_db
class TestLessonSlugUniqueness:
    """ADR-007 §1, and abuse case 8."""

    def test_a_slug_cannot_repeat_within_a_course(self, course, section) -> None:
        _lesson(course, section)

        with pytest.raises(IntegrityError), transaction.atomic():
            _lesson(course, section, position=2, title="Another")

    def test_the_database_refuses_even_across_sections(self, course, section) -> None:
        """The case a per-section constraint would have missed, and the reason
        the redundant course foreign key exists: two sections in one course
        both containing `introduction` would make the lesson URL ambiguous."""
        from apps.catalog.models import Section

        _lesson(course, section)
        other_section = Section.objects.create(course=course, title="Numbers", position=2)

        with pytest.raises(IntegrityError), transaction.atomic():
            _lesson(course, other_section)

    def test_the_same_slug_in_a_different_course_is_fine(self, course, section) -> None:
        """Every course may have an `introduction`; the URL is scoped by course
        slug."""
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Section

        _lesson(course, section)
        other = Course.objects.create(
            slug="french-for-beginners",
            title="French",
            language=course.language,
            level="A1",
            instructor=create_account(
                email="other@example.test", password="a-long-enough-passphrase"
            ),
        )
        other_section = Section.objects.create(course=other, title="Salutations", position=1)

        assert _lesson(other, other_section)


@pytest.mark.django_db
class TestLessonDefaults:
    def test_lessons_are_not_previews_by_default(self, course, section) -> None:
        """Free access is opt-in. A default of True would give the catalogue
        away one forgotten field at a time."""
        assert _lesson(course, section).is_preview is False

    def test_lesson_type_is_an_extensible_enum(self) -> None:
        """ADR-002 §7.5 wants a live session to be a new lesson type later, not
        a boolean bolted on elsewhere."""
        from apps.catalog.models import Lesson

        choices = {value for value, _ in Lesson._meta.get_field("lesson_type").choices}

        assert {"VIDEO", "AUDIO", "TEXT", "RESOURCE"} <= choices
