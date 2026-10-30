"""Transcript reads."""

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Min, Prefetch
from django.utils import timezone

from apps.accounts.privileges import is_platform_administrator, is_signed_in
from apps.transcripts.models import (
    Transcript,
    TranscriptKind,
    TranscriptSegment,
    TranscriptStatus,
)


def transcripts_reviewable_by(*, user):
    """Every transcript this person may review, and nothing else.

    The scope filter invariant 10 asks for. A transcript is addressed by its
    own id, with no course in the path, and the module this feeds used to
    answer that by fetching the row and then calling ``may_review`` in the
    view — which is the fetch-then-check architecture.md §4.4 names as the
    commonest IDOR, and put a business-state ``if`` in a view besides
    (invariant 2).

    Mirrors ``services.may_review``, which mirrors ``media_assets.may_manage``:
    an admin reviews anything, an instructor reviews their own courses.
    ``TestTheReviewScopeAndTheObjectCheckAgree`` pins the two together so
    the duplication cannot drift.
    """
    if not is_signed_in(user):
        return Transcript.objects.none()

    # Joined on both branches. The code this replaced fetched the transcript
    # with `select_related("media_asset__lesson__course")` and dropping it cost
    # **three extra round trips on every review transition** — 11 queries
    # instead of 8 — because `may_review` walks exactly that chain to the
    # course's instructor. Measured by a reviewer, not noticed by writing it,
    # and pinned now by `test_a_transition_costs_no_query_per_hop`.
    reviewable = Transcript.objects.select_related("media_asset__lesson__course")

    if is_platform_administrator(user):
        return reviewable

    return reviewable.filter(media_asset__lesson__course__instructor=user)


def transcript_for_review(*, pk, user):
    """One transcript with its cues, in order — if it is one of theirs.

    Prefetched: a review screen renders every segment, and without this that
    is one query per cue — on a transcript with six hundred of them, which is
    an ordinary hour of speech.

    ``user`` is required rather than optional. An optional scope is one every
    caller may forget, and the two callers of this function are the review
    screen and the response rendered after a review transition — both of which
    must show a transcript only to someone entitled to review it.
    """
    return (
        transcripts_reviewable_by(user=user)
        .filter(pk=pk)
        .select_related("media_asset__lesson__course", "language")
        .prefetch_related(
            Prefetch("segments", queryset=TranscriptSegment.objects.order_by("position"))
        )
        .first()
    )


def segments_editable_by(*, user):
    """Every cue this person may correct, and nothing else.

    The segment half of ``transcripts_reviewable_by``. A ``TranscriptSegment``
    is addressed by its own id with neither a transcript nor a course in the
    path, so without this the view fetches from an unscoped manager and leans
    entirely on ``edit_segment`` to refuse — which it does, but invariant 10
    asks for the queryset to be scoped as well, and a read that depends on a
    later write to be safe is one refactor away from not being.

    Scoped by the same join `transcripts_reviewable_by` uses, one level
    deeper. ``TestTheSegmentReadIsScopedToo`` pins it to the
    predicate.
    """
    if not is_signed_in(user):
        return TranscriptSegment.objects.none()

    editable = TranscriptSegment.objects.select_related("transcript__media_asset__lesson__course")

    if is_platform_administrator(user):
        return editable

    return editable.filter(transcript__media_asset__lesson__course__instructor=user)


def approved_transcript_for(*, lesson):
    """The transcript a learner may be served, or None.

    **APPROVED only**, and this is the control ADR-014 §3 chose instead of a
    publish gate: unreviewed subtitles teach learners the wrong words with
    confidence, so a MACHINE or IN_REVIEW transcript is simply not available.

    ADR-014 §3 also named the risk that comes with putting the whole weight
    here — anything else that renders segments must apply the same filter. So
    the filter lives in this selector rather than in the view, and the next
    reader gets it by calling the same function.
    """
    return (
        Transcript.objects.filter(
            media_asset__lesson=lesson,
            # `language_id`, not `language`: the id is already on the course
            # row the caller joined, whereas the object costs a query to fetch
            # and would be thrown away immediately. ADR-009 — do not add a
            # join you can avoid, and do not pay for one you already have.
            language_id=lesson.course.language_id,
            kind=TranscriptKind.TARGET,
            status=TranscriptStatus.APPROVED,
        )
        # Joined for the panel, which renders the language code. Measured, not
        # assumed (ADR-009): without it the serializer dereferences the foreign
        # key and pays a round trip for one small row. The VTT view does not
        # read it, and a JOIN on a table this size is cheaper than the query it
        # saves — `test_the_panel_does_not_cost_a_query_per_cue` pins both.
        .select_related("language")
        .prefetch_related(
            Prefetch("segments", queryset=TranscriptSegment.objects.order_by("position"))
        )
        .first()
    )


@dataclass(frozen=True)
class UnfinishedTranscriptions:
    """How much transcription work is outstanding, and how old the worst is.

    Two numbers rather than one because they fail differently. A large count
    with a small age is a busy afternoon; a count of one with an age of nine
    days is a job that died and nobody noticed, which is the case
    architecture.md §3.7 means by "stuck transcriptions".
    """

    count: int
    oldest_age: timedelta | None


# FAILED is excluded deliberately. A failed transcription is finished — it has
# a status somebody can act on and M5's dead-letter queue is where it is
# chased. Counting it here would make the metric climb forever after one
# permanent failure and train whoever reads it to ignore the number.
UNFINISHED_STATUSES = (
    TranscriptStatus.PENDING,
    TranscriptStatus.MACHINE,
    TranscriptStatus.IN_REVIEW,
)


def unfinished_transcriptions(*, now=None) -> UnfinishedTranscriptions:
    """Transcription work that has not reached APPROVED or FAILED.

    Lives here rather than in `core.metrics` because nothing outside this app
    may import `Transcript` (ADR-014 §3), and that rule is enforced
    structurally. The metrics collector asks this instead.

    **Read-only**, and one query rather than two: the aggregate returns both
    numbers together, so the count cannot disagree with the age it is reported
    beside.
    """
    now = now or timezone.now()

    aggregate = Transcript.objects.filter(status__in=UNFINISHED_STATUSES).aggregate(
        count=Count("pk"), oldest=Min("created_at")
    )

    oldest = aggregate["oldest"]
    return UnfinishedTranscriptions(
        count=aggregate["count"],
        oldest_age=None if oldest is None else now - oldest,
    )
