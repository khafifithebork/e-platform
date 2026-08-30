"""Asking a provider to transcribe a lesson.

Triggered when a media asset becomes ``READY`` — the moment there is something
transcribable, and not before: submitting a master the video provider is still
transcoding would ask two providers to fetch the same file at once, and one of
them would be reading a URL for media that is not yet whole.

Same shape as M5's processing task, deliberately. A retry assumes the work may
already have happened, the dead-letter queue is a row rather than a log line,
and the backoff is a named function because Celery's eager mode runs retries
inline and never exposes the countdown (ADR-013 §4).
"""

from __future__ import annotations

import json
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.metrics import stuck_transcriptions
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.media_assets.providers.storage import object_storage
from apps.notifications.emails import send_stuck_transcription_alert
from apps.transcripts.models import (
    Transcript,
    TranscriptKind,
    TranscriptSegment,
    TranscriptStatus,
)
from apps.transcripts.providers.base import TranscriptionStatus
from apps.transcripts.providers.fake import transcription_provider

logger = logging.getLogger(__name__)


def retry_countdown(attempt: int) -> int:
    """Seconds before attempt ``attempt``. Exponential, and named so the
    schedule can be asserted — eager mode hides it otherwise."""
    return 2**attempt * 10


def _record_failure(transcript_id, message: str, attempts: int) -> None:
    """Put a transcript in the dead-letter queue.

    Re-fetched by id rather than saved from a stale instance: the task may be
    several retries and minutes away from the object it started with.
    """
    Transcript.objects.filter(pk=transcript_id).update(
        status=TranscriptStatus.FAILED,
        error_message=message[:2000],
        retry_count=attempts,
    )
    logger.error(
        "transcription_failed",
        extra={"transcript_id": str(transcript_id), "attempts": attempts, "error": message},
    )


@shared_task(bind=True, max_retries=None, acks_late=True)
def request_transcription(self, media_asset_id: str) -> str:
    """Submit one media asset for transcription in its course's language.

    The language comes from the **course**, not from the provider guessing.
    A provider told the wrong language transcribes Spanish audio as English
    and produces confident nonsense — which is precisely the harm ADR-014 §3
    is arranged to keep away from learners, arriving by a different route.
    """
    max_retries = settings.TRANSCRIPTION_MAX_RETRIES

    asset = (
        MediaAsset.objects.filter(pk=media_asset_id)
        .select_related("lesson__course__language")
        .first()
    )
    if asset is None:
        # The lesson was deleted while the task sat in the queue. Ordinary.
        return "gone"

    if asset.status != MediaAssetStatus.READY:
        # Something moved it — a replacement upload, a provider failure.
        # Transcribing now would describe media that is being replaced.
        return f"not-ready:{asset.status}"

    language = asset.lesson.course.language

    transcript, _ = Transcript.objects.get_or_create(
        media_asset=asset,
        language=language,
        kind=TranscriptKind.TARGET,
        defaults={"status": TranscriptStatus.PENDING},
    )

    if transcript.provider_job_id:
        # Already submitted. A retry after a timeout would otherwise start a
        # second job we pay for, and whose callback would race the first —
        # the same guard as M5's provider_asset_id check.
        return "already-submitted"

    if transcript.status in (
        TranscriptStatus.MACHINE,
        TranscriptStatus.IN_REVIEW,
        TranscriptStatus.APPROVED,
    ):
        # Human work exists against this transcript. Re-running would replace
        # reviewed words with machine output, which is the one thing review
        # is for.
        return f"already-transcribed:{transcript.status}"

    try:
        source_url = object_storage().presigned_download(
            object_key=asset.source_object_key,
            expires_in=settings.MEDIA_SOURCE_URL_TTL_SECONDS,
        )
        job = transcription_provider().submit(source_url=source_url, language_code=language.code)
    except Exception as exc:
        attempts = self.request.retries + 1
        if attempts > max_retries:
            _record_failure(transcript.pk, f"{type(exc).__name__}: {exc}", attempts - 1)
            return "dead-lettered"

        Transcript.objects.filter(pk=transcript.pk).update(retry_count=attempts)
        raise self.retry(exc=exc, countdown=retry_countdown(attempts)) from exc

    if job.status == TranscriptionStatus.FAILED:
        # Refused on submission. Retrying an unchanged file against an
        # unchanged provider gives the same answer, so this skips the budget.
        _record_failure(transcript.pk, "The provider refused the job.", self.request.retries)
        return "provider-refused"

    with transaction.atomic():
        Transcript.objects.filter(pk=transcript.pk).update(
            provider=job.provider,
            provider_job_id=job.job_id,
            status=TranscriptStatus.PENDING,
            error_message="",
        )

    # Still PENDING. `provider_job_id` being set is what distinguishes
    # "submitted" from "not yet asked" — the same signal M5 uses, and the
    # reason there is no SUBMITTED status to keep in step with a provider's.
    # MACHINE arrives with the callback (T5).
    return "submitted"


@shared_task(bind=True, max_retries=3, acks_late=True)
def apply_transcription_callback(self, webhook_event_id: str) -> str:
    """Turn a verified callback into segments.

    Everything the receiver deliberately does not do, for the reason invariant
    8 gives: a provider retries on any non-2xx, so work in the request turns a
    slow database into a retry storm.

    **It refuses to touch reviewed work.** A callback arriving against a
    transcript somebody has already corrected would replace their words with
    the machine's — the single failure that makes the whole review workflow
    pointless. Late and duplicate callbacks both land here, so that is an
    ordering to expect rather than a hypothetical.
    """
    from apps.core.models import WebhookEvent

    record = WebhookEvent.objects.filter(pk=webhook_event_id).first()
    if record is None:
        return "gone"

    provider = transcription_provider()
    result = provider.parse_webhook(payload=json.dumps(record.payload).encode())

    transcript = Transcript.objects.filter(
        provider=provider.name, provider_job_id=result.job_id
    ).first()
    if transcript is None:
        # A job we have no transcript for: stale, or somebody else's account.
        # Marked processed so it does not sit in the unprocessed queue looking
        # urgent forever.
        WebhookEvent.objects.filter(pk=record.pk).update(processed_at=timezone.now())
        logger.warning("transcription_callback_unknown_job", extra={"job_id": result.job_id})
        return "unknown-job"

    if transcript.status in (TranscriptStatus.IN_REVIEW, TranscriptStatus.APPROVED):
        # Human corrections exist. Marked processed rather than retried,
        # because no amount of retrying makes this the right thing to do.
        WebhookEvent.objects.filter(pk=record.pk).update(processed_at=timezone.now())
        logger.warning(
            "transcription_callback_ignored_reviewed",
            extra={"transcript_id": str(transcript.pk), "status": transcript.status},
        )
        return f"refused-reviewed:{transcript.status}"

    if result.status == TranscriptionStatus.FAILED:
        _record_failure(transcript.pk, "The provider failed to transcribe this audio.", 0)
        outcome = "failed"
    else:
        with transaction.atomic():
            # Replaced rather than appended, which is what makes a redelivered
            # callback idempotent: a second run writes the same segments over
            # the same positions instead of doubling them.
            TranscriptSegment.objects.filter(transcript=transcript).delete()
            TranscriptSegment.objects.bulk_create(
                TranscriptSegment(
                    transcript=transcript,
                    position=segment.position,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                )
                for segment in result.segments
            )
            Transcript.objects.filter(pk=transcript.pk).update(
                status=TranscriptStatus.MACHINE,
                confidence=result.confidence,
                error_message="",
            )
        outcome = "transcribed"

    WebhookEvent.objects.filter(pk=record.pk).update(processed_at=timezone.now())
    return outcome


@shared_task(
    # No retry, the same reasoning as M14 T4's drift alert: if the alert fails
    # to send, the next run is tomorrow and the backlog will still be there. A
    # retry storm against a broken mail provider adds nothing that waiting does
    # not.
    acks_late=True,
)
def alert_on_stuck_transcriptions() -> None:
    """Say something when transcription work has been sitting too long.

    architecture.md §3.7 lists "stuck transcriptions" among the business alerts
    and calls that row *"the one people skip and shouldn't"*. M14 T4 built the
    machinery — Beat, a threshold, email through M11's adapter — and used it for
    entitlement drift only. This is the second thing it was built for.

    **Silent when there is nothing to say.** M14 §6 case 5: an alert that always
    fires is one nobody reads, and a nightly "0 stuck transcriptions" is how a
    real one gets filtered into a folder.

    **Reports; does not repair.** Retrying a transcription costs money at a
    provider. Deciding to spend it is not a cron job's decision — the same line
    T4 drew, for a different reason: there the risk was a second writer of
    entitlement state, here it is a bill.
    """
    report = stuck_transcriptions()
    if report is None:
        logger.info("no stuck transcriptions")
        return

    logger.warning(
        "stuck transcriptions",
        extra={"count": report.count, "oldest_age_days": report.oldest_age_days},
    )

    recipient = settings.OPERATIONS_ALERT_EMAIL
    if not recipient:
        # Configured-off is not an error. The log line above already carries
        # the finding, which is the half that does not depend on anyone having
        # set an address.
        logger.info("no operations alert address configured; nothing sent")
        return

    send_stuck_transcription_alert(to=recipient, report=report)
