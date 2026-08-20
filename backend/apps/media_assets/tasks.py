"""Processing an uploaded master into something playable.

The first task in the project, and the shape the rest should follow.

**The dead-letter queue is the `FAILED` rows.** Celery has none of its own,
and §10 M5 names "no dead-letter queue, so failures vanish silently" as the
mistake for this milestone. So a bounded number of retries, and then a row
carrying the reason, the attempt count and enough context to retry it by hand
— queryable, countable for the business alert §4.3 asks for, and visible in
admin. A traceback in a worker log is not a queue.

**Retries assume the work may already have happened.** A task that timed out
talking to the provider may have been perfectly successful on the provider's
side, and running it again would create a second asset — a second transcode we
pay for, and a playback id nothing references. So the first thing the task
does is ask whether this asset already has a provider copy.
"""

from __future__ import annotations

import json
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.media_assets.providers.fake_video import video_provider
from apps.media_assets.providers.storage import object_storage
from apps.media_assets.providers.video import ProviderAssetStatus

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Processing failed in a way worth retrying."""


def retry_countdown(attempt: int) -> int:
    """Seconds to wait before attempt number ``attempt``.

    Exponential rather than fixed. A provider that is briefly unavailable
    recovers, and retrying every second makes an outage worse while spending
    the whole budget in the seconds before it clears.

    A named function rather than an expression inline, so the schedule can be
    asserted directly — under Celery's eager mode retries run inline and the
    countdown is never observable from the outside.
    """
    return 2**attempt * 10


def _record_failure(asset_id, message: str, attempts: int) -> None:
    """Put an asset in the dead-letter queue.

    Written in its own transaction and re-fetched rather than reusing a model
    instance from the caller: the task may be several retries and minutes away
    from the object it started with, and saving a stale instance would undo
    whatever else touched the row in between.
    """
    MediaAsset.objects.filter(pk=asset_id).update(
        status=MediaAssetStatus.FAILED,
        error_message=message[:2000],
        retry_count=attempts,
    )
    logger.error(
        "media_processing_failed",
        extra={"asset_id": str(asset_id), "attempts": attempts, "error": message},
    )


@shared_task(
    bind=True,
    max_retries=None,  # bounded explicitly below, so the limit is one number
    acks_late=True,
)
def process_media_asset(self, asset_id: str) -> str:
    """Hand a verified master to the video provider.

    Returns a short string describing what happened, so a worker log line says
    which branch was taken rather than only that the task finished.
    """
    max_retries = settings.MEDIA_PROCESSING_MAX_RETRIES

    asset = MediaAsset.objects.filter(pk=asset_id).select_related("lesson").first()
    if asset is None:
        # Not an error worth retrying: the lesson was deleted while the task
        # sat in the queue, which is ordinary.
        return "gone"

    if asset.provider_asset_id:
        # Already handed over. A retry after a timeout would otherwise create a
        # second asset at the provider — one we pay to transcode and store, and
        # whose playback id nothing in our database references.
        return "already-processed"

    if asset.status != MediaAssetStatus.UPLOADED:
        # Something else moved it — a replacement upload, or an admin. Acting
        # now would overwrite that with a stale view of the world.
        return f"not-uploaded:{asset.status}"

    try:
        source_url = object_storage().presigned_download(
            object_key=asset.source_object_key,
            expires_in=settings.MEDIA_SOURCE_URL_TTL_SECONDS,
        )
        created = video_provider().create_asset(source_url=source_url)
    except Exception as exc:
        attempts = self.request.retries + 1
        if attempts > max_retries:
            _record_failure(asset_id, f"{type(exc).__name__}: {exc}", attempts - 1)
            # Swallowed deliberately. The failure is recorded where it can be
            # acted on; re-raising would also mark the task failed in Celery,
            # which nothing reads, and would lose the distinction between "we
            # gave up cleanly" and "the worker died".
            return "dead-lettered"

        MediaAsset.objects.filter(pk=asset_id).update(retry_count=attempts)
        raise self.retry(exc=exc, countdown=retry_countdown(attempts)) from exc

    if created.status == ProviderAssetStatus.ERRORED:
        # The provider looked at it and refused. Retrying an unchanged file
        # against an unchanged provider produces the same answer, so this goes
        # straight to the queue rather than through the retry budget.
        _record_failure(asset_id, "The provider rejected the file.", self.request.retries)
        return "provider-rejected"

    with transaction.atomic():
        MediaAsset.objects.filter(pk=asset_id).update(
            provider=created.provider,
            provider_asset_id=created.asset_id,
            provider_playback_id=created.playback_id,
            status=MediaAssetStatus.TRANSCODING,
            error_message="",
        )

    # TRANSCODING, not READY. The provider reports completion by webhook (T7),
    # and marking it playable here would mint tokens for an asset that is not
    # yet transcoded.
    return "handed-to-provider"


@shared_task(bind=True, max_retries=3, acks_late=True)
def apply_media_webhook(self, webhook_event_id: str) -> str:
    """Act on a verified webhook.

    Everything the receiver deliberately does not do. Separated because a
    provider retries on any non-2xx: work done in the request is work that can
    turn a slow database into a retry storm, and a bug here would look to the
    provider like a delivery failure.

    Idempotent by construction. ``processed_at`` is set at the end, so a task
    redelivered after a worker died re-applies the same state to the same
    asset — which is a no-op — rather than being skipped on the assumption it
    finished.
    """
    from apps.core.models import WebhookEvent

    record = WebhookEvent.objects.filter(pk=webhook_event_id).first()
    if record is None:
        return "gone"

    provider = video_provider()
    event = provider.parse_webhook(payload=json.dumps(record.payload).encode())

    asset = MediaAsset.objects.filter(
        provider=provider.name, provider_asset_id=event.asset_id
    ).first()
    if asset is None:
        # Abuse case 9. A webhook naming an asset we do not have is either a
        # stale event for something deleted, or an event for somebody else's
        # account — and neither is a reason to create a row. Marked processed
        # so it does not sit in the unprocessed queue forever looking urgent.
        WebhookEvent.objects.filter(pk=record.pk).update(processed_at=timezone.now())
        logger.warning(
            "webhook_for_unknown_asset",
            extra={"provider": provider.name, "asset_id": event.asset_id},
        )
        return "unknown-asset"

    if event.status == ProviderAssetStatus.READY:
        # READY is what the playback endpoint checks before minting a token,
        # so this is the moment an asset becomes playable. The database
        # refuses READY without both provider ids, which T6 set.
        MediaAsset.objects.filter(pk=asset.pk).update(
            status=MediaAssetStatus.READY,
            duration_seconds=event.duration_seconds,
            error_message="",
        )

        # Hand off to transcription. Imported inside the function on purpose:
        # apps.transcripts imports this app's models, so a module-level import
        # here would close the cycle. A deferred import is the smaller price
        # than either app knowing less about the other than it needs to.
        #
        # Queued after commit for the same reason every other enqueue is: a
        # worker is a separate process and can read the row before an
        # uncommitted transaction is visible to it, then decline because the
        # asset is not READY yet.
        from apps.transcripts.tasks import request_transcription

        transaction.on_commit(lambda: request_transcription.delay(str(asset.pk)))
        outcome = "ready"
    elif event.status == ProviderAssetStatus.ERRORED:
        _record_failure(asset.pk, "The provider failed to process this file.", asset.retry_count)
        outcome = "failed"
    else:
        # A status we do not model. Recorded and ignored rather than guessed
        # at — mapping an unknown state onto READY would publish something
        # nobody can play.
        logger.info("webhook_status_ignored", extra={"status": event.status})
        outcome = f"ignored:{event.status}"

    WebhookEvent.objects.filter(pk=record.pk).update(processed_at=timezone.now())
    return outcome
