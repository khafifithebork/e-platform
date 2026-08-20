"""Transcript writes — correcting what the machine heard.

The review workflow's whole purpose: a machine transcript of a language lesson
teaches learners the wrong words with confidence, and this is where a human
fixes that.

**Editing an approved transcript sends it back to review.** That lives here
rather than with the other status transitions, because it is a property of
*editing* and not of reviewing: an approval describes the words that were
approved, so changing the words after the fact leaves an approval standing
over content nobody signed off. Deferring it by one task would ship exactly
the window ADR-014 §3 exists to close.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.media_assets.services import may_manage
from apps.transcripts.models import Transcript, TranscriptSegment, TranscriptStatus


class NotYours(Exception):
    """Not a transcript this caller may touch.

    Its own type rather than a message to match on: at the boundary this is a
    404 (§6.3 — never confirm the thing exists) and a state conflict is a 409,
    and deciding that by reading an error string makes the status code depend
    on wording.
    """


class NotEditable(Exception):
    """The transcript is not in a state that accepts edits."""


class InvalidSpan(Exception):
    """The corrected cue would not occupy real time.

    Checked here rather than left to the database. The constraint would refuse
    it either way, but as an IntegrityError surfacing from a save — which
    reaches the client as a 500 for what is plainly a client mistake, and
    tells a reviewer who dragged a handle too far that the server broke.

    The constraint stays, because it is the thing that is actually true; this
    is the boundary translating it into an answer.
    """


# Editing is refused before there are words to edit, and once the provider has
# given up. PENDING means the machine has not answered yet; FAILED means it
# never will, and the fix is a retry rather than typing.
EDITABLE = (
    TranscriptStatus.MACHINE,
    TranscriptStatus.IN_REVIEW,
    TranscriptStatus.APPROVED,
)


def may_review(*, transcript: Transcript, user: User) -> bool:
    """Who may correct this transcript.

    Delegates to the media ownership check rather than restating it. The
    question "may this person manage this lesson's content" already has one
    answer, and a second copy here would be the thing that drifts — ADR-010's
    lesson about entitlement, applied to ownership.

    Deliberately *not* the entitlement resolver: that decides who may read a
    lesson, and a subscriber must not be able to rewrite the teacher's words.
    """
    return may_manage(lesson=transcript.media_asset.lesson, user=user)


@transaction.atomic
def edit_segment(
    *,
    segment: TranscriptSegment,
    by: User,
    text: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> TranscriptSegment:
    """Correct one cue, and mark that a human did.

    ``is_edited`` is set and never cleared. Two things depend on it: a
    reviewer can see which lines have been touched, and a later re-run knows
    there is human work here to preserve rather than replace.

    Timings are editable as well as text, because a reviewer fixing a cue that
    starts half a word late is doing the same job as one fixing a misheard
    verb. The database enforces that the result is still a real span.
    """
    transcript = segment.transcript

    if not may_review(transcript=transcript, user=by):
        raise NotYours

    if transcript.status not in EDITABLE:
        raise NotEditable(f"A transcript in {transcript.status} cannot be edited.")

    if text is not None:
        segment.text = text
    if start_ms is not None:
        segment.start_ms = start_ms
    if end_ms is not None:
        segment.end_ms = end_ms

    # Validated on the *merged* values, not on the payload: a request sending
    # only `start_ms` can still push it past an end it never mentioned.
    if segment.end_ms <= segment.start_ms:
        raise InvalidSpan(
            f"A cue must end after it starts ({segment.start_ms} to {segment.end_ms})."
        )

    segment.is_edited = True
    segment.save(update_fields=["text", "start_ms", "end_ms", "is_edited", "updated_at"])

    _return_to_review(transcript)

    return segment


def _return_to_review(transcript: Transcript) -> None:
    """An edited transcript is no longer the one that was approved.

    Clearing the signature matters as much as the status: leaving
    ``reviewed_by`` and ``approved_at`` in place would let the row keep saying
    who approved it, attributing to them words they never saw. The database
    would allow that — the constraint only requires a signature *when*
    APPROVED — so this is a decision the schema cannot make for us.
    """
    if transcript.status != TranscriptStatus.APPROVED:
        # MACHINE and IN_REVIEW both mean "not approved"; moving MACHINE to
        # IN_REVIEW here would be guessing that an edit is the start of a
        # review, and T7 makes that an explicit act instead.
        return

    Transcript.objects.filter(pk=transcript.pk).update(
        status=TranscriptStatus.IN_REVIEW,
        reviewed_by=None,
        approved_at=None,
    )


class InvalidTransition(Exception):
    """The transcript is not in a state this transition can leave."""


class NothingToApprove(Exception):
    """There are no words here to approve."""


# Every legal move, in one table. Absent means impossible, whoever asks —
# the shape M3's course state machine proved.
#
# There is deliberately no MACHINE -> APPROVED entry. Approving straight from
# machine output is the rubber stamp §10 M6 warns about, and the whole reason
# the review step exists.
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (TranscriptStatus.MACHINE, TranscriptStatus.IN_REVIEW),
        (TranscriptStatus.IN_REVIEW, TranscriptStatus.APPROVED),
        # A reviewer who opened it and changed their mind. Not a failure.
        (TranscriptStatus.IN_REVIEW, TranscriptStatus.MACHINE),
        # An approved transcript that is edited comes back here — written by
        # `_return_to_review` rather than requested, but it is a real move and
        # the table should say so.
        (TranscriptStatus.APPROVED, TranscriptStatus.IN_REVIEW),
    }
)


def _require_transition(transcript: Transcript, target: str) -> None:
    if (transcript.status, target) not in ALLOWED_TRANSITIONS:
        raise InvalidTransition(f"{transcript.status} -> {target}")


@transaction.atomic
def start_review(*, transcript: Transcript, by: User) -> Transcript:
    """Open a machine transcript for correction."""
    if not may_review(transcript=transcript, user=by):
        raise NotYours

    _require_transition(transcript, TranscriptStatus.IN_REVIEW)

    transcript.status = TranscriptStatus.IN_REVIEW
    transcript.save(update_fields=["status", "updated_at"])
    return transcript


@transaction.atomic
def approve(*, transcript: Transcript, by: User) -> Transcript:
    """Sign off a reviewed transcript, and let learners see it.

    **The only route to APPROVED**, and therefore the only route to a learner
    being served subtitles at all (ADR-014 §3). That is why it is one function
    with the signature written inside it rather than a status a caller can
    set.

    Only from IN_REVIEW. What that buys is narrow and worth being honest
    about: it prevents approving a transcript **nobody has opened** — a bulk
    rubber-stamp over raw machine output — not approving one nobody has
    *read*. A reviewer determined to click twice can still do so. The stronger
    guarantee would be per-segment sign-off, which is a product decision about
    reviewer effort rather than a correctness one.
    """
    if not may_review(transcript=transcript, user=by):
        raise NotYours

    _require_transition(transcript, TranscriptStatus.APPROVED)

    if not TranscriptSegment.objects.filter(transcript=transcript).exists():
        # An approved transcript with no cues renders an empty subtitle file,
        # which a player shows as "subtitles available" and then displays
        # nothing — worse than having none, because it looks provided.
        raise NothingToApprove("This transcript has no segments.")

    transcript.status = TranscriptStatus.APPROVED
    transcript.reviewed_by = by
    transcript.approved_at = timezone.now()
    transcript.save(update_fields=["status", "reviewed_by", "approved_at", "updated_at"])
    return transcript


@transaction.atomic
def reopen(*, transcript: Transcript, by: User) -> Transcript:
    """Send a transcript back from review to untouched machine output.

    For a reviewer who opened the wrong lesson. Deliberately not reachable
    from APPROVED: withdrawing an approval is what editing does, and giving it
    a second route would mean two places that must remember to clear the
    signature.
    """
    if not may_review(transcript=transcript, user=by):
        raise NotYours

    _require_transition(transcript, TranscriptStatus.MACHINE)

    transcript.status = TranscriptStatus.MACHINE
    transcript.save(update_fields=["status", "updated_at"])
    return transcript
