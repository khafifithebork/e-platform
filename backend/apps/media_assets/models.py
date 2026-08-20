"""The master we own, and the derived copy a provider holds.

Invariant 7 is the whole design: **R2 holds the master; the video provider
holds a derived copy.** Store ``provider`` and ``provider_asset_id``, never a
playback URL. A URL in a column means switching provider is a data migration
across every lesson plus a hunt through the codebase; an opaque id behind an
adapter means it is one adapter and a backfill script reading masters from
storage (architecture.md §5.2).

That rule is enforced here by a ``CheckConstraint`` rather than left as
something to remember. The tempting mistake is not adding a ``video_url``
column — nobody would — it is putting the URL in the id column because that
happened to be what the provider returned.
"""

from typing import ClassVar

from django.db import models

from apps.catalog.models import Lesson
from apps.core.models import TimestampedModel, UUIDPrimaryKeyModel


class MediaAssetStatus(models.TextChoices):
    """Where an asset is in the pipeline.

    ``PENDING → UPLOADED → TRANSCODING → READY``, with ``FAILED`` reachable
    from any of them. The transitions themselves live in ``services.py``; this
    is only the vocabulary.
    """

    PENDING = "PENDING", "Awaiting upload"
    UPLOADED = "UPLOADED", "Uploaded, not yet processed"
    TRANSCODING = "TRANSCODING", "Being processed by the provider"
    READY = "READY", "Playable"
    FAILED = "FAILED", "Failed"


class MediaAsset(UUIDPrimaryKeyModel, TimestampedModel):
    """One lesson's media, from upload through to playable."""

    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="media_asset",
        help_text="One asset per lesson. Two would be two answers to what plays here.",
    )

    # --- the master, in our storage -------------------------------------
    source_object_key = models.CharField(
        max_length=512,
        help_text="Key in our bucket. Server-generated and random — never a user's filename.",
    )
    source_bytes = models.BigIntegerField()
    source_checksum = models.CharField(max_length=128, blank=True)

    # --- the derived copy, at a provider --------------------------------
    provider = models.CharField(max_length=32)
    provider_asset_id = models.CharField(max_length=128, blank=True)
    provider_playback_id = models.CharField(max_length=128, blank=True)

    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=16,
        choices=MediaAssetStatus.choices,
        default=MediaAssetStatus.PENDING,
    )

    # --- the failure path, which is a deliverable (spec §4) --------------
    #
    # These two columns are the dead-letter queue. Celery has none of its own,
    # and §10 M5 names "failures vanish silently" as the mistake for this
    # milestone — so a failure lands in a table that can be queried, counted
    # for an alert, and retried without re-uploading, because the master is
    # already ours.
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            # The operational question: what is stuck or broken right now.
            models.Index(
                fields=["status", "-created_at"],
                name="media_asset_by_status",
            ),
            # Webhook lookup: a provider event names its own asset id.
            models.Index(fields=["provider", "provider_asset_id"]),
        ]
        constraints: ClassVar[list] = [
            # Invariant 7, in the database. Matched on "://" rather than
            # "http", so an s3:// master URL or an rtmp:// ingest endpoint is
            # caught by the same rule.
            models.CheckConstraint(
                condition=~models.Q(provider_asset_id__contains="://")
                & ~models.Q(provider_playback_id__contains="://"),
                name="provider_ids_are_not_urls",
            ),
            # READY is what the playback-token endpoint checks before minting.
            # An asset claiming to be ready with nothing to play is a 500 on
            # the hottest path, at the moment somebody presses play.
            models.CheckConstraint(
                condition=~models.Q(status=MediaAssetStatus.READY)
                | (~models.Q(provider_asset_id="") & ~models.Q(provider_playback_id="")),
                name="ready_assets_are_playable",
            ),
            # A dead-letter row with no reason is an item nobody can action.
            models.CheckConstraint(
                condition=~models.Q(status=MediaAssetStatus.FAILED) | ~models.Q(error_message=""),
                name="failed_assets_explain_why",
            ),
            # An empty object is a failed upload the browser reported as a
            # success. Without this it reaches the transcoder as a real job.
            models.CheckConstraint(
                condition=models.Q(source_bytes__gt=0),
                name="source_has_bytes",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.status} media for lesson {self.lesson_id}"
