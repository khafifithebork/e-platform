"""A transcription provider that listens to nothing.

Exists so the review workflow and VTT rendering are built and tested before a
transcription provider is chosen and paid for (ADR-014 §1).

**It returns realistic output, and that is the whole point.** A fake returning
a single segment would let every review test and every rendering test pass
while proving nothing about the thing most likely to be wrong: a multi-cue
file, with ordering, non-overlapping timings and the boundaries a player has
to seek between. So this produces several segments, with plausible durations
derived from their word count, a confidence score, and no two cues occupying
the same instant.

Its signing is real, for the same reason M5's is: a fake that accepted any
signature would make the callback's signature test vacuous, which is ADR-006's
inert control in the one place where the control is all that stands between a
forged payload and the words a learner reads.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from django.conf import settings

from apps.transcripts.providers.base import (
    TranscribedSegment,
    TranscriptionJob,
    TranscriptionResult,
    TranscriptionStatus,
    WebhookSignatureInvalid,
)

# What the fake "hears". Real sentences in the target language, of differing
# lengths, so the timings that come out of them differ too — equal-length
# segments would hide an off-by-one in the renderer's cue boundaries.
_UTTERANCES: tuple[str, ...] = (
    "Buenos días, ¿cómo estás?",
    "Me llamo Ana y soy profesora.",
    "Hoy vamos a aprender los saludos.",
    "Repite después de mí, por favor.",
    "Muy bien, eso es todo por hoy.",
)

# Roughly conversational pace. Not a claim about speech — it exists so a cue's
# length follows from its content rather than being a constant.
_MS_PER_WORD = 380
_GAP_MS = 120


def _secret() -> bytes:
    """The key this fake signs with.

    Derived from ``SECRET_KEY``, domain-separated, exactly as M5's fake video
    provider is: a real provider supplies its own signing secret and the real
    adapter will add one, so requiring a variable now for a provider that does
    not exist would make every environment carry it for nothing.
    """
    return hashlib.sha256(f"fake-transcription:{settings.SECRET_KEY}".encode()).digest()


class FakeTranscriptionProvider:
    """Deterministic segments, real signatures, no bill."""

    name = "fake"

    def submit(self, *, source_url: str, language_code: str) -> TranscriptionJob:
        if "://" not in source_url:
            # The provider fetches this itself. A key instead of a URL means
            # the job fails minutes later, somewhere else.
            raise ValueError("source_url must be a URL the provider can fetch")

        return TranscriptionJob(
            provider=self.name,
            job_id=f"fakejob_{secrets.token_urlsafe(12)}",
            status=TranscriptionStatus.PROCESSING,
        )

    def segments(self, *, count: int = len(_UTTERANCES)) -> tuple[TranscribedSegment, ...]:
        """Cues that satisfy every constraint the database imposes.

        Contiguous but never overlapping, with a gap between them: the unique
        position constraint, ``end_ms > start_ms`` and ``start_ms >= 0`` are
        all satisfied by construction, so a test that fails did so because of
        the code under test rather than because the fixture was invalid.
        """
        produced: list[TranscribedSegment] = []
        cursor = 0

        for index in range(count):
            text = _UTTERANCES[index % len(_UTTERANCES)]
            duration = len(text.split()) * _MS_PER_WORD
            produced.append(
                TranscribedSegment(
                    position=index + 1,
                    start_ms=cursor,
                    end_ms=cursor + duration,
                    text=text,
                )
            )
            cursor += duration + _GAP_MS

        return tuple(produced)

    # --- callbacks ------------------------------------------------------

    def sign_webhook(self, *, payload: bytes) -> str:
        """The signature the provider would send. Test-side.

        Hex, so it cannot collide with any separator — the lesson from M5's
        playback token, where a raw digest byte happened to be an ASCII dot
        and one token in eight failed to verify.
        """
        return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()

    def verify_webhook(self, *, payload: bytes, signature: str) -> None:
        expected = self.sign_webhook(payload=payload)
        # Constant-time: a comparison that returns early leaks how much of a
        # forged signature was right, one byte at a time.
        if not hmac.compare_digest(signature, expected):
            raise WebhookSignatureInvalid

    def parse_webhook(self, *, payload: bytes) -> TranscriptionResult:
        body = json.loads(payload)

        return TranscriptionResult(
            job_id=body["job_id"],
            status=body["status"],
            confidence=body.get("confidence"),
            segments=tuple(
                TranscribedSegment(
                    position=segment["position"],
                    start_ms=segment["start_ms"],
                    end_ms=segment["end_ms"],
                    text=segment["text"],
                )
                for segment in body.get("segments", ())
            ),
            payload=body,
        )

    def build_webhook(
        self,
        *,
        job_id: str,
        status: str = TranscriptionStatus.COMPLETED,
        confidence: float | None = 0.94,
        count: int = len(_UTTERANCES),
    ) -> tuple[bytes, str]:
        """A payload and its signature, as the provider would send them.

        Returns both so a test can replay the *same bytes* twice, which is
        what invariant 8's idempotency has to survive — re-signing a freshly
        built payload would produce different content and test nothing.
        """
        segments = self.segments(count=count) if status == TranscriptionStatus.COMPLETED else ()
        body = {
            "job_id": job_id,
            "status": status,
            "confidence": confidence,
            "segments": [
                {
                    "position": segment.position,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text": segment.text,
                }
                for segment in segments
            ],
        }
        payload = json.dumps(body).encode()
        return payload, self.sign_webhook(payload=payload)


def transcription_provider() -> FakeTranscriptionProvider:
    """The provider this process should use.

    The one place that chooses between implementations — ADR-014 §1's claim
    that swapping is a single file rests on nothing else importing a concrete
    provider directly.
    """
    return FakeTranscriptionProvider()
