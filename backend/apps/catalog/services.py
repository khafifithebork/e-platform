"""Catalogue writes.

The publication state machine lives here, in one place, as
``architecture.md`` §10 M3 requires: "model the state machine explicitly with
allowed transitions in a service — not scattered `if status ==` checks".

The scattering is the failure mode worth naming. Once a status check appears in
a view, a serializer and an admin action, the three drift, and the one that
drifts is the one nobody tested.
"""

from typing import ClassVar

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.catalog.models import Course, CourseReviewEvent, CourseStatus


class InvalidTransition(Exception):
    """The course is not in a state this transition can leave."""


class NotPermitted(Exception):
    """The caller may not perform this transition on this course.

    Distinct from ``InvalidTransition`` because they mean different things to
    the caller — and, at the HTTP boundary, produce different answers: a
    forbidden action on a course you do not own must be a 404, not a 403
    (§6.3), because a 403 confirms the course exists.
    """


# Every legal move, in one table. A transition absent here cannot happen,
# whoever asks.
#
# There is deliberately no DRAFT → PUBLISHED entry, for admins or anyone else
# (ADR-007 §2): routing every publish through review is what gives each live
# course a CourseReviewEvent naming who approved it.
ALLOWED_TRANSITIONS: ClassVar[set[tuple[str, str]]] = {
    (CourseStatus.DRAFT, CourseStatus.IN_REVIEW),
    (CourseStatus.IN_REVIEW, CourseStatus.PUBLISHED),
    # Rejection and change requests both return it to the instructor.
    (CourseStatus.IN_REVIEW, CourseStatus.DRAFT),
    (CourseStatus.PUBLISHED, CourseStatus.ARCHIVED),
    # An archived course can be worked on again, but must be reviewed afresh.
    (CourseStatus.ARCHIVED, CourseStatus.DRAFT),
}


def _require_transition(course: Course, target: str) -> None:
    if (course.status, target) not in ALLOWED_TRANSITIONS:
        raise InvalidTransition(f"{course.status} -> {target}")


def _require_owner(course: Course, by: User) -> None:
    if course.instructor_id != by.pk:
        raise NotPermitted


def _require_admin(by: User) -> None:
    if by.role != Role.ADMIN:
        raise NotPermitted


@transaction.atomic
def submit_for_review(*, course: Course, by: User) -> Course:
    """An instructor offers their course for approval.

    The only forward move available to an instructor. They cannot publish, and
    there is no argument here through which they could ask to.
    """
    _require_owner(course, by)
    _require_transition(course, CourseStatus.IN_REVIEW)

    course.status = CourseStatus.IN_REVIEW
    course.save(update_fields=["status", "updated_at"])
    return course


@transaction.atomic
def approve(*, course: Course, by: User, notes: str = "") -> Course:
    """An admin approves a submitted course, which publishes it.

    The only route to PUBLISHED in the system.
    """
    _require_admin(by)
    _require_transition(course, CourseStatus.PUBLISHED)

    course.status = CourseStatus.PUBLISHED
    # Set together with the status: a CheckConstraint requires a published
    # course to carry a date, so these cannot drift apart.
    course.published_at = timezone.now()
    course.save(update_fields=["status", "published_at", "updated_at"])

    CourseReviewEvent.objects.create(
        course=course,
        reviewer=by,
        decision=CourseReviewEvent.Decision.APPROVED,
        notes=notes,
    )
    return course


def _return_to_draft(*, course: Course, by: User, decision: str, notes: str) -> Course:
    _require_admin(by)
    _require_transition(course, CourseStatus.DRAFT)

    course.status = CourseStatus.DRAFT
    # Cleared deliberately. A course that is no longer live must not keep a
    # date that says it is, or every "when did this publish" answer is wrong.
    course.published_at = None
    course.save(update_fields=["status", "published_at", "updated_at"])

    CourseReviewEvent.objects.create(course=course, reviewer=by, decision=decision, notes=notes)
    return course


@transaction.atomic
def reject(*, course: Course, by: User, notes: str = "") -> Course:
    """Send it back as unsuitable."""
    return _return_to_draft(
        course=course, by=by, decision=CourseReviewEvent.Decision.REJECTED, notes=notes
    )


@transaction.atomic
def request_changes(*, course: Course, by: User, notes: str = "") -> Course:
    """Send it back with something specific to fix.

    Same transition as rejection, different decision on the record — the
    instructor needs to know which, and so does anyone reading the history.
    """
    return _return_to_draft(
        course=course,
        by=by,
        decision=CourseReviewEvent.Decision.CHANGES_REQUESTED,
        notes=notes,
    )


@transaction.atomic
def archive(*, course: Course, by: User) -> Course:
    """Withdraw a published course from the catalogue.

    Not a delete. Learners may have progress against its lessons, and §5.4 is
    explicit that deletion is not how content leaves this system.
    """
    _require_admin(by)
    _require_transition(course, CourseStatus.ARCHIVED)

    course.status = CourseStatus.ARCHIVED
    course.published_at = None
    course.save(update_fields=["status", "published_at", "updated_at"])
    return course
