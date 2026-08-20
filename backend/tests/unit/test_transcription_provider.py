"""The transcription provider interface, and the fake behind it.

The tests that matter are about the fake being *realistic enough to be worth
testing against*. ADR-014 §1 committed to that, and it is not decoration: a
fake returning one segment would let every review test and every VTT test pass
while proving nothing about ordering, cue boundaries or overlap — the things
most likely to be wrong in a multi-cue subtitle file.

So the properties asserted here are the ones the rest of M6 will rely on
without re-checking: segments are ordered, non-overlapping, real-length, and
satisfy every constraint the database imposes.
"""

from __future__ import annotations

import itertools
import json

import pytest

from apps.transcripts.providers.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    WebhookSignatureInvalid,
)
from apps.transcripts.providers.fake import FakeTranscriptionProvider, transcription_provider

SOURCE = "https://storage.example.test/masters/abc/def.mp4?signature=x"


@pytest.fixture
def provider():
    return FakeTranscriptionProvider()


class TestTheInterfaceIsSatisfied:
    def test_the_fake_implements_the_protocol(self, provider) -> None:
        assert isinstance(provider, TranscriptionProvider)

    def test_the_factory_returns_a_provider(self) -> None:
        """Nothing else may import a concrete provider — ADR-014 §1's claim
        that swapping is one file rests entirely on that."""
        assert isinstance(transcription_provider(), TranscriptionProvider)


class TestSubmitting:
    def test_a_job_is_opaque_and_processing(self, provider) -> None:
        """PROCESSING, not COMPLETED: transcription of an hour of audio is not
        a request, and a fake that answered immediately would let the pipeline
        skip the callback the whole of T5 exists to handle."""
        job = provider.submit(source_url=SOURCE, language_code="es")

        assert job.status == TranscriptionStatus.PROCESSING
        assert job.job_id.startswith("fakejob_")
        assert "://" not in job.job_id

    def test_two_submissions_get_different_jobs(self, provider) -> None:
        """The job id is how a callback finds its transcript, and the database
        refuses two transcripts sharing one."""
        first = provider.submit(source_url=SOURCE, language_code="es")
        second = provider.submit(source_url=SOURCE, language_code="es")

        assert first.job_id != second.job_id

    def test_an_object_key_is_refused_where_a_url_belongs(self, provider) -> None:
        with pytest.raises(ValueError, match="must be a URL"):
            provider.submit(source_url="masters/abc/def.mp4", language_code="es")


class TestTheSegmentsAreRealisticEnoughToTestAgainst:
    """ADR-014 §1's commitment, asserted rather than assumed."""

    def test_there_are_several(self, provider) -> None:
        """One segment would make every downstream test vacuous."""
        assert len(provider.segments()) >= 3

    def test_they_are_ordered_from_one(self, provider) -> None:
        positions = [segment.position for segment in provider.segments()]

        assert positions == list(range(1, len(positions) + 1))

    def test_no_two_cues_overlap(self, provider) -> None:
        """Overlapping cues render as subtitles that fight each other, and a
        renderer that produced them from ordered input would look correct
        against a single-segment fake."""
        segments = provider.segments()

        for earlier, later in itertools.pairwise(segments):
            assert earlier.end_ms < later.start_ms, (earlier, later)

    def test_every_cue_occupies_real_time(self, provider) -> None:
        for segment in provider.segments():
            assert segment.end_ms > segment.start_ms
            assert segment.start_ms >= 0

    def test_durations_differ(self, provider) -> None:
        """Derived from word count rather than constant. Equal-length cues
        would hide an off-by-one in the renderer's boundaries — every cue
        would look right because every cue looked the same."""
        durations = {segment.end_ms - segment.start_ms for segment in provider.segments()}

        assert len(durations) > 1

    def test_the_text_is_not_placeholder(self, provider) -> None:
        """Real sentences in a target language. "lorem ipsum" would not
        exercise the VTT escaping that T8 needs, and would read as finished
        content if it ever leaked into a fixture someone screenshotted."""
        texts = [segment.text for segment in provider.segments()]

        assert all(texts)
        assert len(set(texts)) == len(texts)

    def test_the_segments_satisfy_the_database(self, db, provider) -> None:
        """The strongest form of "realistic": the fake's output is storable.

        If the fake could produce a segment the constraints reject, every
        downstream test would need to work around it — and the workaround
        would be the thing under test.
        """
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Language, Lesson, Section
        from apps.media_assets.models import MediaAsset, MediaAssetStatus
        from apps.transcripts.models import Transcript, TranscriptSegment

        instructor = create_account(email="t@example.test", password="a-long-passphrase")
        language = Language.objects.create(code="es", name="Spanish", native_name="Esp")
        course = Course.objects.create(
            slug="c", title="C", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="S", position=1)
        lesson = Lesson.objects.create(
            course=course, section=section, slug="l", title="L", position=1
        )
        asset = MediaAsset.objects.create(
            lesson=lesson,
            source_object_key="masters/x/y.mp4",
            source_bytes=1024,
            provider="fake",
            provider_asset_id="fakeasset_x",
            provider_playback_id="fakeplay_x",
            status=MediaAssetStatus.READY,
        )
        transcript = Transcript.objects.create(
            media_asset=asset, language=language, provider="fake"
        )

        TranscriptSegment.objects.bulk_create(
            TranscriptSegment(
                transcript=transcript,
                position=segment.position,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
            )
            for segment in provider.segments()
        )

        assert TranscriptSegment.objects.count() == len(provider.segments())


class TestConfidenceIsAProportion:
    def test_it_is_within_the_bounds_the_database_allows(self, provider) -> None:
        """A provider reporting a percentage would fail the constraint. The
        fake must not be the thing that discovers that in production."""
        payload, _ = provider.build_webhook(job_id="fakejob_1")
        result = provider.parse_webhook(payload=payload)

        assert 0 <= result.confidence <= 1


class TestWebhookSignatures:
    def test_a_genuine_signature_is_accepted(self, provider) -> None:
        """The positive twin. A verifier rejecting everything would pass every
        negative case below."""
        payload, signature = provider.build_webhook(job_id="fakejob_1")

        provider.verify_webhook(payload=payload, signature=signature)

    def test_a_forged_signature_is_refused(self, provider) -> None:
        payload, _ = provider.build_webhook(job_id="fakejob_1")

        with pytest.raises(WebhookSignatureInvalid):
            provider.verify_webhook(payload=payload, signature="0" * 64)

    def test_altered_words_are_refused(self, provider) -> None:
        """The attack this exists for, and it is worse here than for media: a
        forged callback rewrites the words a learner reads as the lesson."""
        payload, signature = provider.build_webhook(job_id="fakejob_1")
        altered = json.loads(payload)
        altered["segments"][0]["text"] = "Something the teacher never said."

        with pytest.raises(WebhookSignatureInvalid):
            provider.verify_webhook(payload=json.dumps(altered).encode(), signature=signature)

    def test_the_signature_is_hex(self, provider) -> None:
        """Hex cannot collide with a separator. M5's playback token joined raw
        digest bytes with b"." and failed one time in eight when a digest byte
        happened to be an ASCII dot; keeping signatures hex means that class
        of bug cannot recur here."""
        _, signature = provider.build_webhook(job_id="fakejob_1")

        assert all(character in "0123456789abcdef" for character in signature)


class TestParsingCallbacks:
    def test_a_payload_becomes_our_vocabulary(self, provider) -> None:
        payload, _ = provider.build_webhook(job_id="fakejob_1")

        result = provider.parse_webhook(payload=payload)

        assert result.job_id == "fakejob_1"
        assert result.status == TranscriptionStatus.COMPLETED
        assert len(result.segments) >= 3

    def test_the_same_payload_parses_identically(self, provider) -> None:
        """What idempotency rests on: two deliveries of one callback must be
        indistinguishable, or the table cannot recognise the replay."""
        payload, _ = provider.build_webhook(job_id="fakejob_1")

        assert provider.parse_webhook(payload=payload) == provider.parse_webhook(payload=payload)

    def test_a_failed_job_carries_no_segments(self, provider) -> None:
        """A failure with segments attached would let a partial transcript be
        written as though it were complete."""
        payload, _ = provider.build_webhook(job_id="fakejob_1", status=TranscriptionStatus.FAILED)

        result = provider.parse_webhook(payload=payload)

        assert result.status == TranscriptionStatus.FAILED
        assert result.segments == ()
