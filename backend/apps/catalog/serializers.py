"""Catalogue I/O shapes. Invariant 2: format only, no business rules."""

from typing import ClassVar

from rest_framework import serializers

from apps.catalog.models import Course


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
