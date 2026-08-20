"""I/O shapes for uploads. Format only (invariant 2).

**ADR-011 audit, done in the same change that gives the fields meaning.**
``status``, ``provider``, ``provider_asset_id``, ``provider_playback_id``,
``source_object_key`` and ``source_bytes`` are every field that will decide
whether a playback token is minted in T8. None is writable by any caller: the
request serializer accepts exactly one field, ``content_type``, and the
response serializer is read-only throughout.

That is the M3 ``is_preview`` failure applied in advance. There, a field was
writable while it was inert and became a giveaway the moment something read
it. Here the fields are inert today and will be read in four tasks' time, so
the audit happens now rather than after.
"""

from typing import ClassVar

from rest_framework import serializers

from apps.media_assets.models import MediaAsset
from apps.media_assets.providers.storage import MAGIC_SIGNATURES


class UploadRequestSerializer(serializers.Serializer):
    """The only thing a client may choose about an upload.

    A closed accept-list rather than free text: an unlisted type has no magic
    signature to check it against, so accepting one would mean accepting bytes
    nothing can verify.
    """

    content_type = serializers.ChoiceField(choices=sorted(MAGIC_SIGNATURES))


class PresignedUploadSerializer(serializers.Serializer):
    """What the browser needs, and nothing reusable beyond this one upload."""

    url = serializers.URLField(read_only=True)
    method = serializers.CharField(read_only=True)
    headers = serializers.DictField(child=serializers.CharField(), read_only=True)
    object_key = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class MediaAssetSerializer(serializers.ModelSerializer):
    """The instructor's view of their own asset.

    ``provider_playback_id`` is absent, deliberately — abuse case 10. It is
    the handle that plays the video, it belongs only inside a minted token,
    and an upload screen has no use for it. A field that appears where it is
    not needed is a field that leaks somewhere it is not checked.
    """

    class Meta:
        model = MediaAsset
        fields: ClassVar[list[str]] = [
            "id",
            "lesson",
            "status",
            "source_bytes",
            "duration_seconds",
            "error_message",
            "retry_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = fields


class UploadTicketSerializer(serializers.Serializer):
    """The pair a caller needs: where to upload, and what it belongs to."""

    asset = MediaAssetSerializer(read_only=True)
    upload = PresignedUploadSerializer(read_only=True)


class PlaybackTokenSerializer(serializers.Serializer):
    """What a player needs, and nothing that outlives the session.

    ``playback_id`` appears here and only here — abuse case 10. It is the
    handle that plays the video, so it goes to a caller the resolver has just
    allowed, and to nobody else: it is absent from the instructor's own asset
    view and from every catalogue response.

    No URL (invariant 7, abuse case 11). The player composes one from the
    handle, so changing provider changes nothing we ever stored or sent.
    ``expires_at`` is included so a player can refresh before playback dies
    mid-lesson rather than discovering the expiry by failing.
    """

    token = serializers.CharField(read_only=True)
    playback_id = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
