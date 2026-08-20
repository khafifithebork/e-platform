"""The transcription callback: invariant 8 again, with a sharper stake.

M5's webhook discipline, applied where a forgery rewrites the words a learner
reads as the lesson rather than a video's processing status.

Three properties carry the weight:

**Reviewed work is never overwritten.** A late or duplicate callback landing
against a corrected transcript would replace a human's words with the
machine's — the one failure that makes the review workflow pointless. Late and
duplicate callbacks are both ordinary, so this is an ordering to expect.

**A redelivery writes the same segments, not twice as many.** Segments are
replaced rather than appended, so re-applying is a no-op rather than a
doubling.

**The provider namespace is separate from media's.** Both fakes are called
"fake" and share one idempotency table; without a prefix a single id collision
would discard one provider's event as a duplicate of the other's, answering
200 while doing nothing.
"""

from __future__ import annotations

import json

import pytest

from apps.accounts.models import Role
from apps.core.models import WebhookEvent
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.transcripts.models import Transcript, TranscriptSegment, TranscriptStatus
from apps.transcripts.providers.base import TranscriptionStatus
from apps.transcripts.providers.fake import FakeTranscriptionProvider

CALLBACK = "/api/v1/webhooks/transcription/"
PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def provider():
    return FakeTranscriptionProvider()


@pytest.fixture
def transcript(db):
    """A submitted transcript, waiting for its words."""
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, Language, Lesson, Section

    instructor = create_account(email="teacher@example.test", password=PASSWORD)
    instructor.role = Role.INSTRUCTOR
    instructor.save(update_fields=["role"])

    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    asset = MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
    )
    return Transcript.objects.create(
        media_asset=asset,
        language=language,
        provider="fake",
        provider_job_id="fakejob_abc",
        status=TranscriptStatus.PENDING,
    )


def _deliver(client, payload: bytes, signature: str):
    return client.post(
        CALLBACK,
        data=payload,
        content_type="application/json",
        HTTP_X_WEBHOOK_SIGNATURE=signature,
    )


def _apply_queued() -> None:
    from apps.transcripts.tasks import apply_transcription_callback

    for record in WebhookEvent.objects.filter(
        processed_at__isnull=True, provider__startswith="transcription:"
    ):
        apply_transcription_callback.apply(args=[str(record.pk)]).get()


class TestTheSignatureIsCheckedFirst:
    def test_a_forged_callback_is_refused(self, client, provider, transcript) -> None:
        payload, _ = provider.build_webhook(job_id="fakejob_abc")

        assert _deliver(client, payload, "0" * 64).status_code == 401

    def test_a_forged_callback_records_nothing(self, client, provider, transcript) -> None:
        payload, _ = provider.build_webhook(job_id="fakejob_abc")

        _deliver(client, payload, "0" * 64)

        assert not WebhookEvent.objects.exists()

    def test_forged_words_never_reach_the_lesson(self, client, provider, transcript) -> None:
        """The reason this matters more here than for media: a forged callback
        rewrites what a learner reads as the lesson."""
        payload, signature = provider.build_webhook(job_id="fakejob_abc")
        altered = json.loads(payload)
        altered["segments"][0]["text"] = "Something the teacher never said."

        response = _deliver(client, json.dumps(altered).encode(), signature)
        _apply_queued()

        assert response.status_code == 401
        assert not TranscriptSegment.objects.exists()

    def test_a_genuine_signature_is_accepted(self, client, provider, transcript) -> None:
        """The positive twin: a verifier refusing everything would pass all
        three tests above."""
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        assert _deliver(client, payload, signature).status_code == 200


class TestApplyingTheResult:
    def test_the_words_arrive_as_segments(self, client, provider, transcript) -> None:
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        _deliver(client, payload, signature)
        _apply_queued()

        segments = list(TranscriptSegment.objects.filter(transcript=transcript))
        assert len(segments) >= 3
        assert [segment.position for segment in segments] == list(range(1, len(segments) + 1))

    def test_the_transcript_becomes_machine(self, client, provider, transcript) -> None:
        """MACHINE, not APPROVED. Unreviewed words are exactly what ADR-014 §3
        keeps from learners."""
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        _deliver(client, payload, signature)
        _apply_queued()

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.MACHINE

    def test_the_confidence_is_recorded(self, client, provider, transcript) -> None:
        payload, signature = provider.build_webhook(job_id="fakejob_abc", confidence=0.91)

        _deliver(client, payload, signature)
        _apply_queued()

        transcript.refresh_from_db()
        assert float(transcript.confidence) == pytest.approx(0.91)

    def test_no_segment_is_marked_edited(self, client, provider, transcript) -> None:
        """Machine output is not a human correction, and `is_edited` is what
        tells a reviewer which lines have been touched."""
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        _deliver(client, payload, signature)
        _apply_queued()

        assert not TranscriptSegment.objects.filter(is_edited=True).exists()

    def test_a_failed_job_lands_in_the_dead_letter_queue(
        self, client, provider, transcript
    ) -> None:
        payload, signature = provider.build_webhook(
            job_id="fakejob_abc", status=TranscriptionStatus.FAILED
        )

        _deliver(client, payload, signature)
        _apply_queued()

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.FAILED
        assert transcript.error_message


class TestIdempotency:
    def test_a_replay_returns_200_and_records_once(self, client, provider, transcript) -> None:
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        first = _deliver(client, payload, signature)
        second = _deliver(client, payload, signature)

        assert (first.status_code, second.status_code) == (200, 200)
        assert WebhookEvent.objects.filter(provider__startswith="transcription:").count() == 1

    def test_applying_twice_does_not_double_the_segments(
        self, client, provider, transcript
    ) -> None:
        """Segments are replaced rather than appended, so a redelivery after a
        worker died rewrites the same rows instead of doubling them — and the
        deferred position constraint would not catch a doubling until commit."""
        from apps.transcripts.tasks import apply_transcription_callback

        payload, signature = provider.build_webhook(job_id="fakejob_abc")
        _deliver(client, payload, signature)
        record = WebhookEvent.objects.get(provider__startswith="transcription:")

        apply_transcription_callback.apply(args=[str(record.pk)]).get()
        count_after_first = TranscriptSegment.objects.count()
        apply_transcription_callback.apply(args=[str(record.pk)]).get()

        assert TranscriptSegment.objects.count() == count_after_first


class TestReviewedWorkIsNeverOverwritten:
    """The guard that makes review worth doing."""

    @pytest.mark.parametrize("status", ["IN_REVIEW", "APPROVED"])
    def test_a_late_callback_leaves_corrections_alone(
        self, client, provider, transcript, status
    ) -> None:
        from django.utils import timezone

        from apps.accounts.services import create_account

        TranscriptSegment.objects.create(
            transcript=transcript,
            position=1,
            start_ms=0,
            end_ms=1000,
            text="What the teacher actually said.",
            is_edited=True,
        )
        signature = (
            {
                "reviewed_by": create_account(email="r@example.test", password=PASSWORD),
                "approved_at": timezone.now(),
            }
            if status == "APPROVED"
            else {}
        )
        Transcript.objects.filter(pk=transcript.pk).update(status=status, **signature)

        payload, sig = provider.build_webhook(job_id="fakejob_abc")
        _deliver(client, payload, sig)
        _apply_queued()

        transcript.refresh_from_db()
        assert transcript.status == status
        assert TranscriptSegment.objects.count() == 1
        assert TranscriptSegment.objects.get().text == "What the teacher actually said."

    def test_the_event_is_still_marked_processed(self, client, provider, transcript) -> None:
        """Refused, not retried: no amount of retrying makes overwriting a
        correction the right thing to do."""
        Transcript.objects.filter(pk=transcript.pk).update(status=TranscriptStatus.IN_REVIEW)
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        _deliver(client, payload, signature)
        _apply_queued()

        assert (
            WebhookEvent.objects.get(provider__startswith="transcription:").processed_at is not None
        )


class TestUnknownJobs:
    def test_a_callback_for_an_unknown_job_creates_nothing(
        self, client, provider, transcript
    ) -> None:
        payload, signature = provider.build_webhook(job_id="fakejob_nobody")

        _deliver(client, payload, signature)
        _apply_queued()

        assert not TranscriptSegment.objects.exists()
        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.PENDING


class TestTheProviderNamespaceIsSeparate:
    """Both fakes are called "fake" and share one idempotency table."""

    def test_transcription_events_are_namespaced(self, client, provider, transcript) -> None:
        payload, signature = provider.build_webhook(job_id="fakejob_abc")

        _deliver(client, payload, signature)

        assert WebhookEvent.objects.get().provider == "transcription:fake"

    def test_a_media_event_with_the_same_id_is_not_a_duplicate(
        self, client, provider, transcript
    ) -> None:
        """The collision the prefix prevents. Without it, one of these two
        would be discarded as a replay of the other — answering 200 while the
        lesson silently never gets its subtitles."""
        from apps.media_assets.providers.fake_video import FakeVideoProvider

        media_payload, media_signature = FakeVideoProvider().build_webhook(
            asset_id="fakeasset_abc", event_id="fakejob_abc"
        )
        client.post(
            "/api/v1/webhooks/video/",
            data=media_payload,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=media_signature,
        )

        payload, signature = provider.build_webhook(job_id="fakejob_abc")
        response = _deliver(client, payload, signature)

        assert response.status_code == 200
        assert WebhookEvent.objects.count() == 2
