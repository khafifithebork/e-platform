"""Choosing a transcription provider. The one file a swap should touch.

The twin of `apps.media_assets.providers`, and it had the identical defect:
`fake.transcription_provider` called itself "the one place that chooses between
implementations — ADR-014 §1's claim that swapping is a single file rests on
nothing else importing a concrete provider directly", while living inside the
concrete provider's own module. Both call sites read

    from apps.transcripts.providers.fake import transcription_provider

**The failure here is quieter than video's and not smaller.** A path left on the
fake produces plausible-looking segments — the fake generates realistic ones on
purpose, so that M6's review workflow could be tested — which then go through
human review and get marked `APPROVED`. Video fails at the moment somebody
presses play. This would fail by publishing invented subtitles under a
reviewer's name.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.transcripts.providers.base import TranscriptionProvider
from apps.transcripts.providers.fake import FakeTranscriptionProvider

PROVIDERS: dict[str, type] = {
    "fake": FakeTranscriptionProvider,
}


def transcription_provider() -> TranscriptionProvider:
    """The provider this process should use.

    An unknown name raises rather than falling back, for the reason in the
    module docstring: the fake's output is designed to be realistic, so a
    silent fallback does not look like a failure at any point a human would
    catch it.
    """
    name = settings.TRANSCRIPTION_PROVIDER

    try:
        implementation = PROVIDERS[name]
    except KeyError:
        raise ImproperlyConfigured(
            f"TRANSCRIPTION_PROVIDER is {name!r}, which is not a transcription "
            f"provider. Known providers: {', '.join(sorted(PROVIDERS))}."
        ) from None

    return implementation()
