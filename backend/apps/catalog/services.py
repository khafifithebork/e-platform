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

from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.db.models import TextField
from django.db.models.functions import Cast
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.accounts.selectors import administrator_emails
from apps.catalog.models import Course, CourseReviewEvent, CourseStatus, Lesson, Section
from apps.core.audit import AdminAction, record_admin_action
from apps.notifications.emails import (
    send_course_reviewed_email,
    send_course_submitted_email,
)


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

    # architecture.md:218. Queued on commit rather than inline: this function
    # is not atomic today, but its callers may become so, and a task that runs
    # before its transaction commits sends mail about something that has not
    # happened — or that then rolls back.
    _notify_reviewers(course)

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

    _notify_instructor_of_review(course, decision="Approved", notes=notes)

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

    _notify_instructor_of_review(
        course,
        decision=(
            "Changes requested"
            if action == CourseReviewEvent.Action.CHANGES_REQUESTED
            else "Rejected"
        ),
        notes=notes,
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


# Weights, and the reason each one is where it is. `A` is the strongest.
#
# Title A, skill areas B, description C. A learner searching "pronunciation"
# wants the course *about* pronunciation above the one that mentions it in a
# paragraph, and without weights those rank identically — a difference no
# functional test can see, because both are returned either way.
#
# The instructor's name is deliberately not indexed. Searching for a person is
# a different feature with different privacy questions, and adding the field
# here would answer them by accident.
SEARCH_WEIGHTS = (("title", "A"), ("skill_areas", "B"), ("description", "C"))


def refresh_search_vector(*, course: Course) -> None:
    """Rebuild one course's search vector. The only writer.

    ADR-020 §3: a stored column written here rather than a database trigger.
    The trade is that a writer bypassing this function leaves the vector stale,
    which `test_a_direct_save_leaves_it_stale` provokes and pins rather than
    describing in a comment.

    Computed **in the database**, not in Python. `to_tsvector` is Postgres's
    own parser and a Python reimplementation would drift from the one the
    query side uses — matching would then depend on which half was written
    last, which is the class of bug that only shows up as "search sometimes
    misses things".

    `skill_areas` is JSON, so it is cast to text before indexing. That indexes
    the punctuation of the JSON array too; the tokeniser discards it, and the
    alternative — unpacking the array in SQL — buys nothing a learner can see.

    Uses `update()`, so `updated_at` does not move. Refreshing a derived column
    is not an edit of the course, and a search reindex that made every course
    look recently changed would corrupt any ordering built on that field.
    """
    vector = None
    for field, weight in SEARCH_WEIGHTS:
        part = SearchVector(Cast(field, TextField()), weight=weight, config="english")
        vector = part if vector is None else vector + part

    Course.objects.filter(pk=course.pk).update(search_vector=vector)


def _notify_reviewers(course: Course) -> None:
    """Tell every administrator a course is waiting.

    On commit, always. `submit_for_review` is not wrapped in a transaction
    today and this fires immediately there — but the guarantee has to belong to
    the notification rather than to whichever caller happens to be atomic, or
    it is a correctness property somebody can remove by adding a decorator
    somewhere else.

    One message per administrator, because the provider interface takes a
    single recipient (`OutboundEmail.to`). A bcc list is how a transactional
    message reaches somebody it was not about.
    """
    title = course.title
    # The address, because there is no name to use: `User` has no name field at
    # all (`display_name` lives on `StudentProfile`, which an instructor need
    # not have). This message goes to administrators, who can already see
    # addresses in diagnostics, so it is the honest identifier rather than a
    # placeholder. See the T7 note about `PublicCourseSerializer`.
    instructor_name = course.instructor.email

    def notify() -> None:
        for address in administrator_emails():
            send_course_submitted_email(
                to=address, course_title=title, instructor_name=instructor_name
            )

    transaction.on_commit(notify)


def _notify_instructor_of_review(course: Course, *, decision: str, notes: str) -> None:
    """Tell the instructor what a reviewer decided.

    On commit, and here it matters: `approve` and `_return_to_draft` are
    atomic, so an inline enqueue could deliver "your course was approved"
    for a transaction that then rolled back.
    """
    address = course.instructor.email
    title = course.title
    cleaned = notes.strip()

    def notify() -> None:
        send_course_reviewed_email(to=address, course_title=title, decision=decision, notes=cleaned)

    transaction.on_commit(notify)
