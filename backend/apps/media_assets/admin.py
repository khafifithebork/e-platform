"""Django Admin for media. Unrouted until M10 (ADR-008 §5).

**This is where the dead-letter queue is read.** §10 M5 names "no dead-letter
queue, so failures vanish silently" as the mistake for this milestone, and a
queue nobody can look at is the same mistake with extra steps. Filtering on
``status`` gives an operator the list of everything that failed, with the
reason and the attempt count beside it.

Read-only throughout, with one action. Editing ``status`` by hand would make
the admin a second writer of pipeline state beside the task and the webhook —
and worse, it could set ``READY`` on an asset the provider never transcoded,
which mints playback tokens for something nobody can play.
"""

from typing import ClassVar

from django.contrib import admin, messages

from apps.core.models import WebhookEvent
from apps.media_assets.models import MediaAsset
from apps.media_assets.services import UploadNotAllowed, retry_processing


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    """The pipeline, and what is stuck in it."""

    list_display: ClassVar[list[str]] = [
        "lesson",
        "status",
        "duration_seconds",
        "retry_count",
        "provider",
        "updated_at",
    ]
    # `status` first: the operator's question is almost always "what failed".
    list_filter: ClassVar[list[str]] = ["status", "provider"]
    search_fields: ClassVar[list[str]] = ["lesson__title", "provider_asset_id"]
    list_select_related: ClassVar[list[str]] = ["lesson"]
    ordering: ClassVar[list[str]] = ["-updated_at"]
    actions: ClassVar[list[str]] = ["retry_failed"]

    # Every field, deliberately. See the module docstring: a writable `status`
    # could mark an asset READY that the provider never transcoded.
    readonly_fields: ClassVar[list[str]] = [
        "lesson",
        "status",
        "source_object_key",
        "source_bytes",
        "source_checksum",
        "provider",
        "provider_asset_id",
        "provider_playback_id",
        "duration_seconds",
        "error_message",
        "retry_count",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request) -> bool:
        # An asset without an uploaded master behind it is a row describing
        # nothing.
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Deleting the row orphans the object in storage: we keep paying for a
        # master nothing references. Removing media means deleting the asset
        # at the provider *and* the object, which is a service, not a button.
        return False

    @admin.action(description="Retry processing")
    def retry_failed(self, request, queryset) -> None:
        """Put failed assets back through the pipeline.

        Per asset rather than in bulk: a selection routinely mixes states, and
        one that cannot be retried must be reported rather than silently
        skipped or allowed to cancel the rest.
        """
        retried = 0
        for asset in queryset:
            try:
                retry_processing(asset=asset)
            except UploadNotAllowed:
                self.message_user(
                    request,
                    f"{asset.lesson}: in {asset.status}, not failed.",
                    level=messages.WARNING,
                )
            else:
                retried += 1

        if retried:
            self.message_user(request, f"{retried} asset(s) requeued.", level=messages.SUCCESS)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    """The idempotency table, readable and nothing else.

    Deleting a row here would let a replayed event be processed a second time —
    the exact thing the unique constraint exists to prevent. It looks like
    tidying up and is a way to double-apply an event.

    ``processed_at`` empty is the useful filter: events received and never
    acted on are either a stuck worker or a bug, and both are worth seeing.
    """

    list_display: ClassVar[list[str]] = [
        "provider",
        "event_type",
        "provider_event_id",
        "created_at",
        "processed_at",
    ]
    list_filter: ClassVar[list[str]] = ["provider", "event_type", "processed_at"]
    search_fields: ClassVar[list[str]] = ["provider_event_id"]
    ordering: ClassVar[list[str]] = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
