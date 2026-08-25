"""Catalogue reads."""

import operator
from functools import reduce

from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db.models import Case, F, IntegerField, Prefetch, Q, Value, When

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


def filtered_published_courses(*, language: str = "", level: str = "", skill_area: str = ""):
    """The catalogue, narrowed. Every filter is optional and they compose.

    Built on `published_courses()` for the same reason search is: that selector
    is the one place the publication rule lives, and a filter is exactly the
    kind of code that grows a second `filter(status=...)` when somebody is in a
    hurry. Abuse case 4 sweeps every combination of these parameters to prove
    no pairing of them is a way past it.

    **Validation is not here.** An unknown level or a language code that does
    not exist is rejected by the query serializer before this is called, so
    this function narrows and never has to decide what a bad value means. The
    reason that matters: the tempting behaviour for an unrecognised filter is
    to ignore it, which returns the whole catalogue and looks to the caller
    exactly like a filter that worked.

    `skill_areas` is JSONB and matched with `contains`, which uses the column
    rather than pulling every row into Python. There is no index on it — with
    a curated catalogue of hundreds it does not need one, and adding a GIN
    index nobody has measured a need for is the guess ADR-009 forbids.
    """
    courses = published_courses()

    if language:
        courses = courses.filter(language__code=language)
    if level:
        courses = courses.filter(level=level)
    if skill_area:
        courses = courses.filter(skill_areas__contains=[skill_area])

    return courses


# ADR-020 §6. Six, because a related strip is a nudge rather than a second
# catalogue — a learner who wants the whole list has the catalogue.
RELATED_LIMIT = 6


def related_courses(*, course: Course, limit: int = RELATED_LIMIT):
    """Published courses a learner looking at this one might also want.

    **A rule, not a recommender** (ADR-020 §6). Same language is a hard filter;
    within it, more shared skill areas ranks higher, then the same level, then
    the most recently published. Collaborative filtering needs enrolment volume
    this product does not have, and a recommender trained on ten enrolments
    recommends noise — which reads as a broken product rather than an empty
    one.

    **Same language is a filter rather than a rank** because the alternative is
    worse than useless: a learner studying Spanish shown a French course has
    been given a row of things they cannot use, and no amount of ranking below
    that saves it.

    Overlap is counted in SQL, one `CASE` per skill area the course carries.
    Doing it in Python means loading every course in the language to sort a
    handful, which is fine at a hundred courses and is the shape that stops
    being fine silently. There are few skill areas per course, so the
    expression stays small.

    Built on `published_courses()` — abuse case 2 is the same rule as case 1
    with a second reader, and a second reader is exactly where it gets
    forgotten.
    """
    candidates = published_courses().filter(language=course.language).exclude(pk=course.pk)

    areas = [area for area in (course.skill_areas or []) if isinstance(area, str)]
    if areas:
        # One `Case` per area, **added together**. A single `Case` with several
        # `When`s returns the first branch that matches, so it answers "shares
        # at least one" — which is 1 for a course sharing all five areas and 1
        # for a course sharing one. That was the first version here, and
        # `test_more_shared_skill_areas_ranks_higher` caught it because the
        # weaker candidate was deliberately the more recent one.
        #
        # Not `Sum`: that is an aggregate and would collapse the queryset. This
        # is arithmetic across columns of a single row.
        overlap = reduce(
            operator.add,
            [
                Case(
                    When(skill_areas__contains=[area], then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
                for area in areas
            ],
        )
    else:
        # No skill areas to share. Ranking then rests on level and recency,
        # which is still better than an empty strip.
        overlap = Value(0, output_field=IntegerField())

    return list(
        candidates.annotate(
            shared=overlap,
            same_level=Case(
                When(level=course.level, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by("-shared", "-same_level", "-published_at")[:limit]
    )
