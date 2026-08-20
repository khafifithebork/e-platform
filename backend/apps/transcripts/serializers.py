"""Transcript I/O shapes. Format only (invariant 2).

**ADR-011 audit, in the change that gives the fields meaning.** `status`,
`provider`, `provider_job_id`, `confidence`, `reviewed_by` and `approved_at`
all decide something — whether a learner is served subtitles (T9), whether a
re-run may overwrite (T4), who signed an approval — and none of them is
writable by any caller. The reviewer's serializer accepts exactly three
fields: the text and the two timings.

`provider_job_id` is absent from every output shape (abuse case 11). It is a
support handle, and an instructor's review screen has no use for it.
"""

from typing import ClassVar

from rest_framework import serializers

from apps.transcripts.models import Transcript, TranscriptSegment


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSegment
        fields: ClassVar[list[str]] = [
            "id",
            "position",
            "start_ms",
            "end_ms",
            "text",
            "is_edited",
        ]
        read_only_fields: ClassVar[list[str]] = fields


class SegmentEditSerializer(serializers.Serializer):
    """What a reviewer may change about a cue.

    All optional: a reviewer fixing only the text should not have to resend
    timings they did not touch, and requiring them invites a client to echo
    stale values back over somebody else's concurrent edit.
    """

    text = serializers.CharField(required=False, allow_blank=False)
    start_ms = serializers.IntegerField(required=False, min_value=0)
    end_ms = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Nothing to change.")
        return attrs


class TranscriptSerializer(serializers.ModelSerializer):
    """A transcript as its reviewer sees it, segments included.

    Nested rather than a separate call: a review screen needs every cue at
    once, and paginating them would make "read the lesson end to end" — the
    actual task — into a loop.
    """

    segments = SegmentSerializer(many=True, read_only=True)
    language_code = serializers.CharField(source="language.code", read_only=True)

    class Meta:
        model = Transcript
        fields: ClassVar[list[str]] = [
            "id",
            "lesson",
            "language_code",
            "kind",
            "status",
            "confidence",
            "approved_at",
            "error_message",
            "segments",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = fields

    lesson = serializers.UUIDField(source="media_asset.lesson_id", read_only=True)
