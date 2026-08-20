"""Requesting transcription when media becomes ready.

The handoff between M5 and M6, and the guards that keep it from doing damage
when it runs twice — which it will, because a task that timed out talking to a
provider may have succeeded on the provider's side.

Two guards matter more than the rest.

**A second submission must not start a second job.** We would pay for both,
and the two callbacks would race to write the same transcript.

**A re-run must never overwrite reviewed words.** Human corrections are the
entire point of the review workflow; machine output replacing them is the one
failure that makes review pointless rather than merely late.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.transcripts.models import Transcript, TranscriptStatus

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture
def asset(db):
    """A transcoded lesson, ready to be transcribed."""
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
    return MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
    )


def _run(asset_id) -> str:
    from apps.transcripts.tasks import request_transcription

    return request_transcription.apply(args=[str(asset_id)]).get()


class TestSubmitting:
    def test_a_ready_asset_is_submitted(self, asset) -> None:
        assert _run(asset.pk) == "submitted"

        transcript = Transcript.objects.get(media_asset=asset)
        assert transcript.provider == "fake"
        assert transcript.provider_job_id.startswith("fakejob_")

    def test_it_stays_pending_until_the_callback(self, asset) -> None:
        """MACHINE means words exist. Setting it at submission would let the
        review workflow open on a transcript with no segments in it."""
        _run(asset.pk)

        assert Transcript.objects.get(media_asset=asset).status == TranscriptStatus.PENDING

    def test_the_course_language_is_what_is_requested(self, asset) -> None:
        """From the course, not from the provider guessing. A provider told
        the wrong language transcribes Spanish as English and produces
        confident nonsense — the harm ADR-014 §3 keeps from learners,
        arriving by another route."""
        from apps.transcripts.providers.fake import FakeTranscriptionProvider

        seen = {}
        original = FakeTranscriptionProvider.submit

        def record(self, *, source_url, language_code):
            seen["language"] = language_code
            return original(self, source_url=source_url, language_code=language_code)

        with patch.object(FakeTranscriptionProvider, "submit", record):
            _run(asset.pk)

        assert seen["language"] == "es"

    def test_the_provider_is_given_a_url_it_can_fetch(self, asset) -> None:
        """Invariant 6: the provider pulls the master itself, so audio never
        passes through Django on the way out."""
        from apps.transcripts.providers.fake import FakeTranscriptionProvider

        seen = {}
        original = FakeTranscriptionProvider.submit

        def record(self, *, source_url, language_code):
            seen["url"] = source_url
            return original(self, source_url=source_url, language_code=language_code)

        with patch.object(FakeTranscriptionProvider, "submit", record):
            _run(asset.pk)

        assert seen["url"].startswith("http")
        assert "def.mp4" in seen["url"]


class TestItDoesNotActTwice:
    def test_a_second_run_does_not_start_a_second_job(self, asset) -> None:
        """We would pay for both, and the two callbacks would race to write
        the same transcript."""
        _run(asset.pk)
        first_job = Transcript.objects.get(media_asset=asset).provider_job_id

        assert _run(asset.pk) == "already-submitted"

        assert Transcript.objects.get(media_asset=asset).provider_job_id == first_job

    def test_only_one_transcript_is_ever_created(self, asset) -> None:
        """The database refuses a second per language and kind, so a task
        creating rather than get_or_creating would fail loudly — but it would
        fail in a worker, at midnight."""
        _run(asset.pk)
        _run(asset.pk)

        assert Transcript.objects.filter(media_asset=asset).count() == 1

    @pytest.mark.parametrize("status", ["MACHINE", "IN_REVIEW", "APPROVED"])
    def test_it_never_overwrites_human_work(self, asset, status) -> None:
        """The guard that matters most. Re-running against a reviewed
        transcript would replace corrected words with machine output, which
        makes review pointless rather than merely late."""
        from django.utils import timezone

        from apps.accounts.services import create_account
        from apps.catalog.models import Language

        transcript = Transcript.objects.create(
            media_asset=asset,
            language=Language.objects.get(code="es"),
            provider="fake",
        )
        # APPROVED needs a signature, or `approved_transcript_is_signed`
        # refuses the row — the constraint caught this test before the test
        # caught anything, which is the constraint working.
        signature = (
            {
                "reviewed_by": create_account(email="reviewer@example.test", password=PASSWORD),
                "approved_at": timezone.now(),
            }
            if status == "APPROVED"
            else {}
        )
        Transcript.objects.filter(pk=transcript.pk).update(status=status, **signature)

        assert _run(asset.pk) == f"already-transcribed:{status}"

        transcript.refresh_from_db()
        assert transcript.status == status
        assert transcript.provider_job_id is None

    def test_an_asset_that_is_not_ready_is_left_alone(self, asset) -> None:
        """A replacement upload put it back mid-flight. Transcribing now would
        describe media that is being replaced."""
        MediaAsset.objects.filter(pk=asset.pk).update(status=MediaAssetStatus.TRANSCODING)

        assert _run(asset.pk) == "not-ready:TRANSCODING"
        assert not Transcript.objects.exists()

    def test_a_deleted_asset_is_not_an_error(self, asset) -> None:
        asset_id = asset.pk
        asset.delete()

        assert _run(asset_id) == "gone"


class TestTheDeadLetterQueue:
    def test_a_persistent_failure_is_recorded(self, asset, settings) -> None:
        """A FAILED transcript with no reason is the silent failure §10 M5
        named, wearing a different status."""
        from apps.transcripts.providers.fake import FakeTranscriptionProvider

        settings.TRANSCRIPTION_MAX_RETRIES = 0

        with patch.object(
            FakeTranscriptionProvider, "submit", side_effect=RuntimeError("provider is down")
        ):
            assert _run(asset.pk) == "dead-lettered"

        transcript = Transcript.objects.get(media_asset=asset)
        assert transcript.status == TranscriptStatus.FAILED
        assert "provider is down" in transcript.error_message

    def test_the_failure_record_survives(self, asset, settings) -> None:
        """The T4-of-M5 bug, in the place it would recur: a failure written
        inside a transaction that then unwinds leaves the queue empty while
        looking like it works."""
        from apps.transcripts.providers.fake import FakeTranscriptionProvider

        settings.TRANSCRIPTION_MAX_RETRIES = 0

        with patch.object(FakeTranscriptionProvider, "submit", side_effect=RuntimeError("boom")):
            _run(asset.pk)

        assert Transcript.objects.filter(status=TranscriptStatus.FAILED).count() == 1

    def test_a_transient_failure_recovers(self, asset, settings) -> None:
        """Asserted through the outcome, not by watching for a Retry: eager
        mode runs retries inline, so a test looking for the exception reports
        "did not raise" against code that is retrying correctly (ADR-013 §4).
        """
        from apps.transcripts.providers.base import TranscriptionJob, TranscriptionStatus
        from apps.transcripts.providers.fake import FakeTranscriptionProvider

        settings.TRANSCRIPTION_MAX_RETRIES = 3
        recovered = TranscriptionJob(
            provider="fake", job_id="fakejob_recovered", status=TranscriptionStatus.PROCESSING
        )

        with patch.object(
            FakeTranscriptionProvider,
            "submit",
            side_effect=[RuntimeError("briefly down"), recovered],
        ):
            _run(asset.pk)

        assert Transcript.objects.get(media_asset=asset).provider_job_id == "fakejob_recovered"

    def test_the_backoff_grows(self) -> None:
        from apps.transcripts.tasks import retry_countdown

        assert [retry_countdown(attempt) for attempt in (1, 2, 3)] == [20, 40, 80]


class TestTheHandoffFromMedia:
    """M5 hands off here when an asset becomes READY."""

    def test_a_ready_webhook_queues_transcription(
        self, asset, django_capture_on_commit_callbacks
    ) -> None:
        """Without this the pipeline stops after transcoding and nothing says
        so — the lesson is playable and permanently unsubtitled."""
        from apps.core.models import WebhookEvent
        from apps.media_assets.tasks import apply_media_webhook

        MediaAsset.objects.filter(pk=asset.pk).update(status=MediaAssetStatus.TRANSCODING)
        record = WebhookEvent.objects.create(
            provider="fake",
            provider_event_id="fakeevt_1",
            event_type="video.asset.ready",
            payload={
                "id": "fakeevt_1",
                "type": "video.asset.ready",
                "asset_id": "fakeasset_abc",
                "status": "READY",
                "duration_seconds": 90,
            },
        )

        with (
            patch("apps.transcripts.tasks.request_transcription.delay") as queued,
            django_capture_on_commit_callbacks(execute=True),
        ):
            apply_media_webhook.apply(args=[str(record.pk)]).get()

        assert queued.called
        assert queued.call_args.args == (str(asset.pk),)
