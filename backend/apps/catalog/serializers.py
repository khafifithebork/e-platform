"""Catalogue I/O shapes. Invariant 2: format only, no business rules."""

from typing import ClassVar

from rest_framework import serializers

from apps.catalog.models import Course, CourseReviewEvent, Lesson, Section


class CourseSerializer(serializers.ModelSerializer):
    """An instructor's view of their own course.

    ``status``, ``published_at`` and ``instructor`` are read-only, and that is
    a security control rather than a convenience. A writable ``status`` would
    hand every instructor the publish button — the one thing
    ``architecture.md`` §3 promises they do not have — and a writable
    ``instructor`` would let them assign a course to somebody else, or claim
    one.

    Ownership comes from the session in ``perform_create``, never from the
    request body.
    """

    class Meta:
        model = Course
        fields: ClassVar[list[str]] = [
            "id",
            "slug",
            "title",
            "description",
            "language",
            "level",
            "skill_areas",
            "status",
            "published_at",
            "instructor",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = [
            "id",
            "status",
            "published_at",
            "instructor",
            "created_at",
            "updated_at",
        ]


class SectionSerializer(serializers.ModelSerializer):
    """``course`` is read-only: it comes from the URL, never the body.

    A writable ``course`` would let an instructor post a section into somebody
    else's course by id, which is precisely the hole the scoped queryset closes
    everywhere else.
    """

    class Meta:
        model = Section
        fields: ClassVar[list[str]] = [
            "id",
            "course",
            "title",
            "position",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = ["id", "course", "created_at", "updated_at"]


class LessonSerializer(serializers.ModelSerializer):
    """``section`` is writable, and the view narrows its queryset to the course
    in the URL — see ``InstructorLessonViewSet.get_serializer``. That is what
    turns another course's section id into a 400 rather than a cross-course
    write, a constraint the database cannot express because both rows are
    individually valid.
    """

    class Meta:
        model = Lesson
        fields: ClassVar[list[str]] = [
            "id",
            "course",
            "section",
            "slug",
            "title",
            "body",
            "lesson_type",
            "position",
            "is_preview",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = ["id", "course", "created_at", "updated_at"]


class ReorderSerializer(serializers.Serializer):
    """Shape only. Whether the ids are *yours* is decided in the service."""

    order = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


class LessonReorderSerializer(ReorderSerializer):
    section = serializers.UUIDField()


class CourseReviewEventSerializer(serializers.ModelSerializer):
    """Read-only in both directions.

    Every field is read-only *and* the viewset is read-only. That is
    deliberate belt-and-braces: if someone later swaps the base class for a
    ModelViewSet — the obvious "while I'm here" change — the serializer still
    refuses to write, and an instructor still cannot forge their own approval.
    """

    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = CourseReviewEvent
        fields: ClassVar[list[str]] = [
            "id",
            "course",
            "actor",
            "actor_email",
            "action",
            "notes",
            "created_at",
        ]
        read_only_fields: ClassVar[list[str]] = fields
