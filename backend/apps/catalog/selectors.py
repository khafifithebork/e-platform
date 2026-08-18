"""Catalogue reads."""

from django.db.models import Prefetch

from apps.accounts.models import User
from apps.catalog.models import (
    Course,
    CourseReviewEvent,
    CourseStatus,
    Language,
    Lesson,
    Section,
)


def courses_for_instructor(*, user: User):
    """Every course this instructor owns, and nothing else.

    The scope filter is the whole security control for the instructor API.
    ``architecture.md`` §10 names its absence as the mistake for this milestone,
    and §4.4 calls fetching by primary key without one the most common IDOR in
    DRF codebases.

    Because the filter is applied to the queryset the detail, update and delete
    views all resolve through, a course belonging to someone else is not
    forbidden — it is *not found*, which is what §6.3 requires. A 403 would
    confirm it exists.

    Joined on language and instructor: a list of courses renders both, and
    without the join that is two extra queries per row.
    """
    return (
        Course.objects.filter(instructor=user)
        .select_related("language", "instructor")
        .order_by("-created_at")
    )


def sections_for_course(*, course: Course):
    """A course's sections in their curriculum order.

    Ordering comes from ``Meta.ordering`` on the model, and is restated here so
    that a later change to the default cannot silently reorder the curriculum a
    student sees.
    """
    return Section.objects.filter(course=course).order_by("position")


def lessons_for_course(*, course: Course):
    """A course's lessons, ordered by section then position.

    Joined on section: a lesson list renders the section it sits in, and
    without the join that is one extra query per lesson.
    """
    return (
        Lesson.objects.filter(course=course)
        .select_related("section")
        .order_by("section__position", "position")
    )


def review_events_for_course(*, course: Course):
    """A course's review history, newest first.

    Joined on actor: the trail is read to find out *who*, and without the join
    that is one query per row.
    """
    return (
        CourseReviewEvent.objects.filter(course=course)
        .select_related("actor")
        .order_by("-created_at")
    )


def published_courses():
    """The catalogue as the public sees it.

    One filter, in one place, used by every public view. Abuse cases 5 and 6
    both reduce to this queryset being the only way a request reaches a course
    — a second, hand-rolled filter somewhere else is how a DRAFT eventually
    leaks.

    Ordered by ``-published_at`` to match the partial index on published rows,
    and because "newest first" is what a catalogue means.
    """
    return (
        Course.objects.filter(status=CourseStatus.PUBLISHED)
        .select_related("language", "instructor")
        .order_by("-published_at")
    )


def published_course_detail(*, slug: str) -> Course:
    """One published course, with its curriculum, or ``DoesNotExist``.

    Prefetched: a detail page renders every section and every lesson, which is
    one query per section without this.
    """
    return (
        published_courses()
        .prefetch_related(
            Prefetch("sections", queryset=Section.objects.order_by("position")),
            Prefetch("sections__lessons", queryset=Lesson.objects.order_by("position")),
        )
        .get(slug=slug)
    )


def languages_with_published_courses():
    """Languages the visitor can actually browse.

    Offering a language with nothing published gives the visitor a dead end
    and gives everyone else a free list of what is being worked on.
    """
    return (
        Language.objects.filter(courses__status=CourseStatus.PUBLISHED).distinct().order_by("name")
    )
