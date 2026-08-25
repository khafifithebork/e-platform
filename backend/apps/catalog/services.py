"""Catalogue writes.

The publication state machine lives here, in one place, as
``architecture.md`` §10 M3 requires: "model the state machine explicitly with
allowed transitions in a service — not scattered `if status ==` checks".

The scattering is the failure mode worth naming. Once a status check appears in
a view, a serializer and an admin action, the three drift, and the one that
drifts is the one nobody tested.
"""

from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.catalog.models import Course, CourseReviewEvent, CourseStatus, Lesson, Section
from apps.core.audit import AdminAction, record_admin_action


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


#: Which administrative action each review decision records. A dict rather
#: than branching at the call site, so a new review decision that forgets its
#: audit action fails with a KeyError here instead of silently writing nothing.
_AUDIT_FOR_REVIEW_ACTION = {
    CourseReviewEvent.Action.REJECTED: AdminAction.COURSE_REJECTED,
    CourseReviewEvent.Action.CHANGES_REQUESTED: AdminAction.COURSE_CHANGES_REQUESTED,
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

    # Written only after the transition is allowed, so a refused submission
    # leaves no trace — the review queue orders on these rows, and a rejected
    # attempt in the trail would put the course in the wrong place.
    CourseReviewEvent.objects.create(
        course=course,
        actor=by,
        action=CourseReviewEvent.Action.SUBMITTED,
    )
    return course


@transaction.atomic
def approve(*, course: Course, by: User, notes: str = "", request=None) -> Course:
    """An admin approves a submitted course, which publishes it.

    The only route to PUBLISHED in the system.

    Writes two rows, and they are not duplicates (ADR-018 §8). The
    `CourseReviewEvent` is the course's own history, shown to the instructor
    who submitted it. The audit row is the administrative trail, read when
    answering "what has this account done" — §8 lists course approval among
    the actions that must appear there.
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
        actor=by,
        action=CourseReviewEvent.Action.APPROVED,
        notes=notes,
    )
    record_admin_action(
        actor=by,
        action=AdminAction.COURSE_APPROVED,
        target=course,
        # An approval usually carries no note, and M3 does not ask for one —
        # unlike a rejection, where the instructor needs to know what to fix.
        # Saying so plainly beats a template like "approved for publication",
        # which would read as a justification nobody actually gave.
        reason=notes.strip() or "Approved with no notes recorded",
        request=request,
        course_slug=course.slug,
    )
    return course


def _return_to_draft(*, course: Course, by: User, action: str, notes: str, request=None) -> Course:
    _require_admin(by)
    _require_transition(course, CourseStatus.DRAFT)

    course.status = CourseStatus.DRAFT
    # Cleared deliberately. A course that is no longer live must not keep a
    # date that says it is, or every "when did this publish" answer is wrong.
    course.published_at = None
    course.save(update_fields=["status", "published_at", "updated_at"])

    CourseReviewEvent.objects.create(course=course, actor=by, action=action, notes=notes)
    record_admin_action(
        actor=by,
        action=_AUDIT_FOR_REVIEW_ACTION[action],
        target=course,
        # Always the reviewer's own words here: M3 requires notes for both of
        # these, because an instructor sent back with nothing to fix has been
        # told nothing.
        reason=notes.strip() or "Returned to draft with no notes recorded",
        request=request,
        course_slug=course.slug,
    )
    return course


@transaction.atomic
def reject(*, course: Course, by: User, notes: str = "", request=None) -> Course:
    """Send it back as unsuitable."""
    return _return_to_draft(
        course=course,
        by=by,
        action=CourseReviewEvent.Action.REJECTED,
        notes=notes,
        request=request,
    )


@transaction.atomic
def request_changes(*, course: Course, by: User, notes: str = "", request=None) -> Course:
    """Send it back with something specific to fix.

    Same transition as rejection, different decision on the record — the
    instructor needs to know which, and so does anyone reading the history.
    """
    return _return_to_draft(
        course=course,
        by=by,
        action=CourseReviewEvent.Action.CHANGES_REQUESTED,
        notes=notes,
        request=request,
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


class InvalidReorder(Exception):
    """The submitted order does not name exactly the rows being reordered."""


def _apply_order(*, queryset, ordered_ids: Sequence[UUID]) -> None:
    """Rewrite ``position`` to match ``ordered_ids``, or change nothing.

    Two things make this worth a service rather than a loop in a view.

    The first is *all or nothing*. A reorder payload is a list of ids, which
    makes it the easiest place in the API to smuggle in a row belonging to
    somebody else. Validating each id as it is applied would leave the caller's
    own rows half-moved when the foreign one is rejected — so the membership
    check runs against the whole set first, before a single write. The set
    comparison catches both directions at once: an id that does not belong
    here, and an id that belongs here but was left out. Omission matters
    because a row not named keeps a position another row is about to take.

    The second is that the intermediate state is illegal. Swapping positions 1
    and 2 passes through a moment where both rows hold the same value, which
    the unique constraint forbids. ``bulk_update`` hides that for small inputs
    by writing the whole permutation in one UPDATE — PostgreSQL checks a
    deferrable constraint at end of statement, so a single-statement
    permutation is never caught mid-way. That is luck, not design, and it runs
    out: ``bulk_update`` splits into batches once the list is long enough, and
    between two batches the duplicate is committed-visible within the
    transaction.

    ``section_position_unique_per_course`` and
    ``lesson_position_unique_per_section`` are therefore DEFERRABLE, which
    postpones the check to commit and covers the split case as well as any
    future refactor to per-row saves. The alternative is a sentinel pass
    through negative positions — two writes per row, and debris if it fails
    half way. ``test_a_row_by_row_swap_needs_the_deferred_constraint`` and its
    twin pin this down; the deferral is invisible under test rollback
    otherwise.

    ``select_for_update`` serialises concurrent reorders of the same parent.
    Without it two requests can each read consistent positions, each write a
    valid permutation, and interleave into one that is neither.
    """
    rows = {row.pk: row for row in queryset.select_for_update()}

    submitted = list(ordered_ids)
    if len(submitted) != len(set(submitted)) or set(submitted) != set(rows):
        raise InvalidReorder(
            "The order must name every item being reordered, exactly once, and nothing else."
        )

    for position, pk in enumerate(submitted, start=1):
        rows[pk].position = position

    queryset.model.objects.bulk_update(rows.values(), ["position", "updated_at"])


@transaction.atomic
def reorder_sections(*, course: Course, ordered_ids: Sequence[UUID]) -> None:
    """Reorder a course's sections. Scoping is the caller's job, above this."""
    _apply_order(queryset=Section.objects.filter(course=course), ordered_ids=ordered_ids)


@transaction.atomic
def reorder_lessons(*, section: Section, ordered_ids: Sequence[UUID]) -> None:
    """Reorder one section's lessons.

    Scoped to a section, not a course, because the uniqueness of ``position``
    is per section — a course-wide reorder would have to know which section
    each lesson belongs to and would silently move lessons between them.
    """
    _apply_order(queryset=Lesson.objects.filter(section=section), ordered_ids=ordered_ids)
