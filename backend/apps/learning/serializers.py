"""Learning I/O shapes. Format only (invariant 2).

**ADR-011 audit.** ``completed_at``, ``max_position_seconds`` and
``watched_seconds`` each decide something — whether a lesson reads as
finished, whether it can complete, how far somebody got — and none is
writable. A client sends a playhead and a delta; everything else is derived by
the service.

``watched_seconds`` in particular must not be settable directly, or a client
could post the lesson's duration once and complete it instantly. That is not
fraud prevention (ADR-016 §2) so much as keeping the number mean what it says.
"""

from typing import ClassVar

from rest_framework import serializers

from apps.learning.models import Enrollment, LessonProgress


class HeartbeatSerializer(serializers.Serializer):
    """One report from a player.

    ``watched_delta_seconds`` is bounded here as well as clamped in the
    service. The serializer rejects nonsense loudly with a 400; the service
    clamps quietly, because it is also reachable from code that is not a
    request.
    """

    position_seconds = serializers.IntegerField(min_value=0)
    watched_delta_seconds = serializers.IntegerField(min_value=0, max_value=3600)


class LessonProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonProgress
        fields: ClassVar[list[str]] = [
            "lesson",
            "last_position_seconds",
            "max_position_seconds",
            "watched_seconds",
            "completed_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = fields


class EnrollmentSerializer(serializers.ModelSerializer):
    """A course in progress, as "my courses" shows it.

    ``completed_lesson_count`` is annotated rather than stored (ADR-016 §3),
    so it appears here as a read-only integer with no column behind it.
    """

    course_slug = serializers.SlugField(source="course.slug", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    completed_lesson_count = serializers.IntegerField(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Enrollment
        fields: ClassVar[list[str]] = [
            "id",
            "course_slug",
            "course_title",
            "last_lesson",
            "completed_lesson_count",
            "lesson_count",
            "started_at",
            "completed_at",
        ]
        read_only_fields: ClassVar[list[str]] = fields
