"""Catalogue reads."""

from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db.models import F, Prefetch, Q

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


# ADR-020 §4: the top N by rank, and no pagination. Rank is a function of the
# query, so there is no stored column for a cursor to page on, and this
# codebase does not use offset pagination on public surfaces.
SEARCH_LIMIT = 50

# Longer than any real search. The bound exists because `to_tsquery` work grows
# with the number of terms, and an anonymous endpoint that will happily parse a
# 50KB query is a way to spend our CPU for the price of one request.
MAX_QUERY_LENGTH = 200

# pg_trgm's own documented default for `similarity_threshold`. Used rather than
# chosen: a number invented here would be a guess presented as a tuning
# decision, and §6 is explicit about not inventing provider behaviour.
TRIGRAM_THRESHOLD = 0.3


def search_published_courses(*, query: str, limit: int = SEARCH_LIMIT):
    """Published courses matching `query`, best first.

    **Full text first; trigram only if that returns nothing** (ADR-020 §5).
    Unioning the two makes every search pay for both and lets a fuzzy match
    outrank an exact one, which is the behaviour users report as "the search is
    broken" without being able to say why. The fallback exists for typos, and a
    typo is the case where full text returns zero rows.

    Built on `published_courses()`, not on `Course.objects`. That selector is
    the single place the publication filter lives, and abuse cases 1 and 2 both
    reduce to search never being a second way in — a hand-rolled
    `filter(status=...)` here is how a draft eventually leaks.

    Returns a list, not a queryset: the caller must not be able to bolt further
    filtering onto something already sliced, and the slice is the deliberate
    cap rather than an implementation detail.
    """
    # Control characters are stripped before anything else, and NUL is the one
    # that matters: PostgreSQL text cannot contain 0x00, so `?q=%00` reached the
    # driver and returned a **500** — an unauthenticated one-request crash of
    # the catalogue's search. Found by abuse case 5, which is why that case
    # lists control characters and not only long input.
    #
    # Stripped rather than rejected: nobody types a NUL, so a 400 would only
    # tell an attacker their probe was noticed. The remaining text still
    # searches.
    cleaned = "".join(ch for ch in (query or "") if ch.isprintable() or ch.isspace())
    cleaned = cleaned.strip()[:MAX_QUERY_LENGTH]
    if not cleaned:
        return []

    # `websearch_to_tsquery`, not `plainto_tsquery`: it accepts quoted phrases
    # and `-exclusions` the way a person expects a search box to behave, and it
    # never raises on malformed input. `to_tsquery` would — an unbalanced
    # parenthesis from a visitor becomes a 500.
    search = SearchQuery(cleaned, search_type="websearch", config="english")

    matches = list(
        published_courses()
        .filter(search_vector=search)
        .annotate(rank=SearchRank(F("search_vector"), search))
        .order_by("-rank", "-published_at")[:limit]
    )
    if matches:
        return matches

    return list(
        published_courses()
        .annotate(similarity=TrigramSimilarity("title", cleaned))
        .filter(similarity__gte=TRIGRAM_THRESHOLD)
        .order_by("-similarity", "-published_at")[:limit]
    )
