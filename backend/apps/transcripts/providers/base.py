"""The transcription provider interface — written before any vendor code.

Third instance of the pattern (billing in M4, video in M5), and the reasoning
is unchanged: the interface is what keeps the provider replaceable, an adapter
never touches the ORM, and the vocabulary is ours.

**Nothing here models Deepgram.** It is named in `architecture.md` but has not
been signed up for, and §6 forbids inventing a provider's capabilities. M6
ships this interface and a fake (ADR-014 §1); a real adapter translates into
these shapes rather than these shapes being modelled on documentation nobody
has read.

The unit is a **segment**, because invariant 13 stores rows and renders VTT
from them. An adapter that returned a caption file would have to be parsed
back into rows, which is the transformation the invariant exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class TranscriptionStatus:
    """What a provider can tell us about a job, in our words."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TranscribedSegment:
    """One cue as the provider heard it.

    Times in **milliseconds**, matching the columns. Providers commonly report
    floating-point seconds; converting at the adapter boundary means rounding
    happens once, in one place, rather than differently in the renderer and
    the player.
    """

    position: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class TranscriptionJob:
    """A submitted job. The id is how a callback finds its transcript."""

    provider: str
    job_id: str
    status: str


@dataclass(frozen=True)
class TranscriptionResult:
    """A finished job, normalised.

    ``confidence`` is a proportion, 0 to 1 — the database refuses anything
    else, so an adapter reporting a percentage fails at the constraint rather
    than being read as certainty by whatever surfaces it in review.
    """

    job_id: str
    status: str
    confidence: float | None = None
    segments: tuple[TranscribedSegment, ...] = ()
    payload: dict = field(default_factory=dict)


class WebhookSignatureInvalid(Exception):
    """The payload did not come from the provider, or was altered."""


@runtime_checkable
class TranscriptionProvider(Protocol):
    """What any transcription provider must do for us."""

    name: str

    def submit(self, *, source_url: str, language_code: str) -> TranscriptionJob:
        """Ask for a transcription of media the provider fetches itself.

        A URL, not bytes: invariant 6 forbids media passing through Django,
        and the provider pulls from our storage exactly as the video provider
        does. The URL is short-lived and read-only.

        Asynchronous by contract — the result arrives by callback. A provider
        that answered synchronously would still be modelled this way, because
        transcription of an hour of audio is not a request.
        """
        ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> None:
        """Raise ``WebhookSignatureInvalid`` unless the payload is authentic.

        Invariant 8 puts this first, before the event is recorded. An
        unverified callback is an unauthenticated write to lesson content —
        and content is what learners read, so a forged one is worse here than
        a forged media event.
        """
        ...

    def parse_webhook(self, *, payload: bytes) -> TranscriptionResult:
        """Normalise a verified payload. Never called before verification."""
        ...
