"""Catalogue reads."""

from django.db.models import Prefetch, Q

from apps.accounts.models import Role, User
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

    Not joined on language or instructor, despite rendering both. The
    instructor serializer emits them as primary keys, which come from the
    ``_id`` columns already on the row — nothing dereferences the related
    object, so ``select_related`` here bought two JOINs per page and saved
    nothing. Measured, not assumed: the list costs the same three queries with
    it and without. ``test_query_counts`` pins that, so the join can be added
    back the moment a serializer nests either relation.
    """
    return Course.objects.filter(instructor=user).order_by("-created_at")


def sections_for_course(*, course: Course):
    """A course's sections in their curriculum order.

    Ordering comes from ``Meta.ordering`` on the model, and is restated here so
    that a later change to the default cannot silently reorder the curriculum a
    student sees.
    """
    return Section.objects.filter(course=course).order_by("position")


def lessons_for_course(*, course: Course):
    """A course's lessons, ordered by section then position.

    The ordering needs the section, so the join happens either way — but as an
    ORDER BY, not a ``select_related``. The serializer emits ``section`` as a
    primary key and never dereferences it, so selecting the related row would
    widen every result for nothing. Same reasoning as
    ``courses_for_instructor``, and pinned by the same test.
    """
    return Lesson.objects.filter(course=course).order_by("section__position", "position")


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


def lessons_visible_to(*, user):
    """Lessons a caller may attempt to read at all.

    Visibility, not entitlement — two different questions, answered in two
    places on purpose. This one asks "does this content exist for you"; the
    resolver then asks "may you see its contents". Merging them would put
    catalogue rules inside ``resolve_access`` and course status into a
    function that is only about subscriptions.

    The distinction matters concretely: without this filter a paying
    subscriber passes the resolver's SUBSCRIPTION_ACTIVE branch on a lesson in
    an unpublished course, and reads a draft the instructor has not submitted.
    The resolver is not wrong to allow it — it was never asked about
    publication.

    Instructors keep their own drafts, because writing a course means reading
    it back. Admins see everything, as they do everywhere else.
    """
    published = Q(course__status=CourseStatus.PUBLISHED)

    if user is None or not getattr(user, "is_authenticated", False):
        visible = published
    elif getattr(user, "role", None) == Role.ADMIN or getattr(user, "is_superuser", False):
        visible = Q()
    else:
        visible = published | Q(course__instructor=user)

    return Lesson.objects.filter(visible).select_related("course").distinct()
