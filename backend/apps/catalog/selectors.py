"""Catalogue reads."""

from apps.accounts.models import User
from apps.catalog.models import Course, Lesson, Section


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
