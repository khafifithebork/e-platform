"""Transcript reads."""

from django.db.models import Prefetch

from apps.transcripts.models import Transcript, TranscriptSegment


def transcript_for_review(*, pk):
    """One transcript with its cues, in order.

    Prefetched: a review screen renders every segment, and without this that
    is one query per cue — on a transcript with six hundred of them, which is
    an ordinary hour of speech.
    """
    return (
        Transcript.objects.filter(pk=pk)
        .select_related("media_asset__lesson__course", "language")
        .prefetch_related(
            Prefetch("segments", queryset=TranscriptSegment.objects.order_by("position"))
        )
        .first()
    )
