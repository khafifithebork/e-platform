"""The publication state machine.

The product's central promise lives here. `architecture.md` §3 calls the
catalogue curated and admin-approved, so the interesting tests are not the ones
that publish a course — they are the ones that try to and are refused.

ADR-006: each guard is provoked, not merely configured. A transition table
nobody consults would read exactly like this one and let an instructor publish
their own work.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role


@pytest.fixture
def instructor(db):
    from apps.accounts.services import create_account

    user = create_account(email="teacher@example.test", password="a-long-enough-passphrase")
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def other_instructor(db):
    from apps.accounts.services import create_account

    user = create_account(email="rival@example.test", password="a-long-enough-passphrase")
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def admin(db):
    from apps.accounts.services import create_account

    user = create_account(email="editor@example.test", password="a-long-enough-passphrase")
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def course(db, instructor):
    from apps.catalog.models import Course, Language

    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    return Course.objects.create(
        slug="spanish-for-beginners",
        title="Spanish for beginners",
        language=language,
        level="A1",
        instructor=instructor,
    )


@pytest.mark.django_db
class TestSubmitForReview:
    def test_the_owner_may_submit_a_draft(self, course, instructor) -> None:
        from apps.catalog.services import submit_for_review

        submit_for_review(course=course, by=instructor)
        course.refresh_from_db()

        assert course.status == "IN_REVIEW"

    def test_another_instructor_may_not(self, course, other_instructor) -> None:
        from apps.catalog.services import NotPermitted, submit_for_review

        with pytest.raises(NotPermitted):
            submit_for_review(course=course, by=other_instructor)

        course.refresh_from_db()
        assert course.status == "DRAFT"

    def test_it_cannot_be_submitted_twice(self, course, instructor) -> None:
        from apps.catalog.services import InvalidTransition, submit_for_review

        submit_for_review(course=course, by=instructor)

        with pytest.raises(InvalidTransition):
            submit_for_review(course=course, by=instructor)


@pytest.mark.django_db
class TestOnlyAdminsPublish:
    """The promise the product is built on."""

    def test_an_instructor_cannot_publish_their_own_course(self, course, instructor, admin) -> None:
        from apps.catalog.services import NotPermitted, approve, submit_for_review

        submit_for_review(course=course, by=instructor)

        with pytest.raises(NotPermitted):
            approve(course=course, by=instructor)

        course.refresh_from_db()
        assert course.status == "IN_REVIEW"
        assert course.published_at is None

    def test_an_instructor_cannot_publish_someone_elses_course(
        self, course, instructor, other_instructor
    ) -> None:
        from apps.catalog.services import NotPermitted, approve, submit_for_review

        submit_for_review(course=course, by=instructor)

        with pytest.raises(NotPermitted):
            approve(course=course, by=other_instructor)

    def test_an_admin_publishes_from_review(self, course, instructor, admin) -> None:
        from apps.catalog.services import approve, submit_for_review

        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin)
        course.refresh_from_db()

        assert course.status == "PUBLISHED"
        assert course.published_at is not None

    def test_an_admin_cannot_publish_a_draft_directly(self, course, admin) -> None:
        """ADR-007 §2: the only path to PUBLISHED is through review, so every
        live course has a review event naming who approved it."""
        from apps.catalog.services import InvalidTransition, approve

        with pytest.raises(InvalidTransition):
            approve(course=course, by=admin)


@pytest.mark.django_db
class TestReviewActionsAreRecorded:
    def test_approval_records_who_and_when(self, course, instructor, admin) -> None:
        """§7.2. "Why is this live?" has to be answerable later."""
        from apps.catalog.models import CourseReviewEvent
        from apps.catalog.services import approve, submit_for_review

        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin, notes="Good pacing.")

        # Named by action: the submission is on the trail too, and a bare
        # get() would break every time a new step is recorded.
        event = CourseReviewEvent.objects.get(course=course, action="APPROVED")
        assert event.action == "APPROVED"
        assert event.actor == admin
        assert event.notes == "Good pacing."

    def test_rejection_returns_it_to_draft_and_records_why(self, course, instructor, admin) -> None:
        from apps.catalog.models import CourseReviewEvent
        from apps.catalog.services import reject, submit_for_review

        submit_for_review(course=course, by=instructor)
        reject(course=course, by=admin, notes="Audio is inaudible in lesson 3.")
        course.refresh_from_db()

        assert course.status == "DRAFT"
        assert course.published_at is None
        assert CourseReviewEvent.objects.filter(course=course, action="REJECTED").exists()

    def test_archiving_clears_published_at(self, course, instructor, admin) -> None:
        """A course that is no longer live must not keep a date saying it is,
        or every "when did this publish" answer afterwards is wrong.

        Archive rather than reject, because a published course cannot be
        rejected — the only move out of PUBLISHED is ARCHIVED.
        """
        from apps.catalog.services import approve, archive, submit_for_review

        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin)
        archive(course=course, by=admin)
        course.refresh_from_db()

        assert course.status == "ARCHIVED"
        assert course.published_at is None


@pytest.mark.django_db
class TestArchive:
    def test_only_an_admin_archives(self, course, instructor, admin) -> None:
        from apps.catalog.services import NotPermitted, approve, archive, submit_for_review

        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin)

        with pytest.raises(NotPermitted):
            archive(course=course, by=instructor)

    def test_a_draft_cannot_be_archived(self, course, admin) -> None:
        from apps.catalog.services import InvalidTransition, archive

        with pytest.raises(InvalidTransition):
            archive(course=course, by=admin)


@pytest.mark.django_db
class TestTheTableHasNoDirectPublishRoute:
    def test_published_is_reachable_only_from_review(self) -> None:
        """Belt and braces on the guards above: if a future edit adds a
        DRAFT → PUBLISHED entry, this fails even if no test calls it."""
        from apps.catalog.services import ALLOWED_TRANSITIONS

        sources = {source for source, target in ALLOWED_TRANSITIONS if target == "PUBLISHED"}

        assert sources == {"IN_REVIEW"}
