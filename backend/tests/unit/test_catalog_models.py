"""Language and Course.

The status field is the one that carries the product. `architecture.md` §3
describes the catalogue as curated and admin-approved, so a course reaching
`PUBLISHED` by any route other than an admin's approval falsifies that
sentence. These tests pin the shape; the transitions themselves are T2.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction


@pytest.fixture
def instructor(db):
    from apps.accounts.models import Role
    from apps.accounts.services import create_account

    user = create_account(email="teacher@example.test", password="a-long-enough-passphrase")
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def language(db):
    from apps.catalog.models import Language

    return Language.objects.create(code="es", name="Spanish", native_name="Español")


class TestLanguage:
    def test_code_is_the_natural_key(self) -> None:
        from apps.catalog.models import Language

        assert Language._meta.get_field("code").unique is True

    def test_uses_an_integer_primary_key(self) -> None:
        """architecture.md §5.2: UUIDs are for things whose ids appear in URLs
        and could be enumerated. A language list is public by definition."""
        from apps.catalog.models import Language

        assert Language._meta.pk.get_internal_type() != "UUIDField"


@pytest.mark.django_db
class TestLanguageRows:
    def test_two_languages_cannot_share_a_code(self, language) -> None:
        from apps.catalog.models import Language

        with pytest.raises(IntegrityError), transaction.atomic():
            Language.objects.create(code="es", name="Castilian", native_name="Castellano")

    def test_languages_start_active(self, language) -> None:
        assert language.is_active is True


class TestCourseShape:
    def test_uses_a_uuid_primary_key(self) -> None:
        """`/courses/47` would tell a competitor how many courses exist."""
        from apps.catalog.models import Course

        assert Course._meta.pk.get_internal_type() == "UUIDField"

    def test_new_courses_are_drafts(self) -> None:
        from apps.catalog.models import Course

        assert Course._meta.get_field("status").default == "DRAFT"

    def test_the_four_states(self) -> None:
        from apps.catalog.models import Course

        choices = {value for value, _ in Course._meta.get_field("status").choices}

        assert choices == {"DRAFT", "IN_REVIEW", "PUBLISHED", "ARCHIVED"}

    def test_levels_are_the_cefr_scale(self) -> None:
        from apps.catalog.models import Course

        choices = {value for value, _ in Course._meta.get_field("level").choices}

        assert choices == {"A1", "A2", "B1", "B2", "C1", "C2"}

    def test_deleting_an_instructor_is_refused_while_they_have_courses(self) -> None:
        """PROTECT, not CASCADE (§5.4). Deleting a user must not silently take
        published courses — and their learners' progress — with it. It forces a
        real deactivation flow instead."""
        from django.db import models

        from apps.catalog.models import Course

        assert Course._meta.get_field("instructor").remote_field.on_delete is models.PROTECT

    def test_published_at_is_not_set_by_default(self) -> None:
        from apps.catalog.models import Course

        assert Course._meta.get_field("published_at").null is True


@pytest.mark.django_db
class TestCourseRows:
    def _course(self, instructor, language, **overrides):
        from apps.catalog.models import Course

        return Course.objects.create(
            **{
                "slug": "spanish-for-beginners",
                "title": "Spanish for beginners",
                "description": "An introduction.",
                "language": language,
                "level": "A1",
                "instructor": instructor,
                **overrides,
            }
        )

    def test_a_new_course_is_an_unpublished_draft(self, instructor, language) -> None:
        course = self._course(instructor, language)

        assert course.status == "DRAFT"
        assert course.published_at is None

    def test_slugs_are_unique_across_the_catalogue(self, instructor, language) -> None:
        """The slug is the public URL, so it cannot collide even between
        different instructors."""
        self._course(instructor, language)

        with pytest.raises(IntegrityError), transaction.atomic():
            self._course(instructor, language, title="Another course")

    def test_skill_areas_default_to_empty(self, instructor, language) -> None:
        assert self._course(instructor, language).skill_areas == []


@pytest.mark.django_db
class TestPublishedCoursesAreIndexed:
    def test_there_is_an_index_for_the_catalogue_query(self) -> None:
        """§5.3 calls (status, language, level) the hottest query in the app.

        Asserted because an index is invisible until it is missing, and then it
        is invisible until the catalogue is slow.
        """
        from apps.catalog.models import Course

        indexed = {tuple(index.fields) for index in Course._meta.indexes}

        assert ("status", "language", "level") in indexed
