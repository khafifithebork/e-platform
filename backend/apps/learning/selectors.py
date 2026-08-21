"""Learning reads (invariant 2).

Every function here is scoped to one learner. There is no selector that takes
a user id as data — the caller passes the requesting user, the same shape the
progress endpoints use, so that "whose progress is this" is never a question a
URL gets to answer.

**Nothing here consults the entitlement resolver, deliberately.** An enrolment
is a record of what somebody watched, not a grant (ADR-016 §1), and a learner
whose subscription has lapsed must still be able to see the courses they were
partway through — that list is the surface that asks them to come back. The
lessons themselves stay gated at the point of playback, where they always were.
"""

from __future__ import annotations

from django.db.models import Count, Max, OuterRef, Q, Subquery

from apps.accounts.models import User
from apps.catalog.models import Course, Lesson
from apps.learning.models import Enrollment, LessonProgress


def _completed_lesson_ids(user: User):
    """Lessons this learner has finished, as a subquery rather than a list.

    Evaluating it in Python would send every completed lesson id back to the
    database as a literal on the next query, which grows with how much somebody
    has studied — the one number that only ever goes up.
    """
    return LessonProgress.objects.filter(user=user, completed_at__isnull=False).values("lesson_id")


def _next_lesson_id(user: User):
    """The first lesson of the course not yet completed, in curriculum order.

    Correlated on the enrolment's course, so a list of enrolments costs one
    query rather than one per row (ADR-009).

    "First not completed" rather than "the one after the bookmark": a learner
    who skipped ahead has a bookmark past lessons they never watched, and
    sending them onward would quietly write those off. This walks back to the
    earliest gap instead.
    """
    return Subquery(
        Lesson.objects.filter(course_id=OuterRef("course_id"))
        .exclude(pk__in=_completed_lesson_ids(user))
        .order_by("section__position", "position")
        .values("pk")[:1]
    )


def courses_in_progress(*, user: User):
    """Every course this learner has started, for "my courses".

    ``completed_lesson_count`` is annotated, not stored (ADR-016 §3). §5.2 of
    the architecture document defaults to a denormalised counter, and this
    inverts that on purpose: the counter there is for catalogue cards, which
    aggregate across every course, while this one is per enrolment for the
    handful one person is taking. The same section says denormalised counters
    "always drift eventually", and a number that can disagree with the rows it
    summarises is worse than a join here.

    ``distinct=True`` does the real work on ``lesson_count`` and not much on
    the other. Both counts read one join chain — course to lessons to *every*
    learner's progress — so once a second learner has watched the course, each
    lesson arrives more than once and a plain count reports a four-lesson
    course as having eight. ``test_counts_survive_the_join`` provokes that with
    a classmate; with a single learner the join is one-to-one and a
    non-distinct count is accidentally right, which is how this would otherwise
    ship looking tested.

    On ``completed_lesson_count`` it is belt-and-braces: the ``FILTER`` narrows
    to one learner, and ``one_progress_row_per_lesson`` means that is at most
    one row per lesson, so there is nothing to deduplicate. Kept because the
    word costs nothing and the alternative is a count in this file whose
    correctness depends on a constraint in another.

    Ordering is left to the paginator, which is fixed on ``-created_at, -pk``
    because a cursor needs a stable, unique, indexed column and an aggregate is
    none of those. ``last_activity`` therefore ships as data rather than as
    order — enough for a "continue learning" row to pick the right course out of
    a page, and honest about the fact that it is not a sort key.
    """
    mine = Q(course__lessons__progress__user=user)
    completed = mine & Q(course__lessons__progress__completed_at__isnull=False)

    return (
        Enrollment.objects.filter(user=user)
        .select_related("course")
        # The serializer renders the course's slug and title, so this join is
        # the difference between one query and one per enrolment. Measured, not
        # assumed — `test_my_courses_costs_the_same_for_one_course_or_ten`.
        .annotate(
            lesson_count=Count("course__lessons", distinct=True),
            completed_lesson_count=Count("course__lessons", filter=completed, distinct=True),
            last_activity=Max("course__lessons__progress__updated_at", filter=mine),
            next_lesson=_next_lesson_id(user),
        )
    )


def next_lesson_for(*, user: User, course: Course) -> Lesson | None:
    """What to play next in one course, or ``None`` when nothing is left.

    ``None`` means every lesson is complete. It is deliberately not an error
    and deliberately not the last lesson repeated: "you have finished" is a
    thing the caller needs to be able to say.
    """
    return (
        Lesson.objects.filter(course=course)
        .exclude(pk__in=_completed_lesson_ids(user))
        .order_by("section__position", "position")
        .first()
    )
