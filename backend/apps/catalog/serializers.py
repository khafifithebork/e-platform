"""Catalogue I/O shapes. Invariant 2: format only, no business rules."""

from typing import ClassVar

from rest_framework import serializers

from apps.catalog.models import Course, CourseReviewEvent, Language, Lesson, Section


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


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields: ClassVar[list[str]] = ["code", "name", "native_name"]


class PublicLessonSerializer(serializers.ModelSerializer):
    """A lesson as an anonymous visitor sees it: a title and a shape.

    ``body`` is absent from ``fields``, not hidden by a condition. Entitlements
    arrive in M4 and there is nothing to gate with yet, so the safe form is a
    serializer that has no way to render paid content at all — a field that is
    usually hidden is one wrong branch from being visible.
    """

    class Meta:
        model = Lesson
        fields: ClassVar[list[str]] = [
            "id",
            "slug",
            "title",
            "lesson_type",
            "position",
            "is_preview",
        ]


class PublicSectionSerializer(serializers.ModelSerializer):
    lessons = PublicLessonSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields: ClassVar[list[str]] = ["id", "title", "position", "lessons"]


class PublicCourseSerializer(serializers.ModelSerializer):
    """A catalogue card.

    ``instructor_name`` rather than the instructor's id or email: the
    catalogue is unauthenticated, and an email address on a public page is a
    spam list.
    """

    language = LanguageSerializer(read_only=True)
    instructor_name = serializers.CharField(source="instructor.get_full_name", read_only=True)

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
            "instructor_name",
            "published_at",
        ]


class PublicCourseDetailSerializer(PublicCourseSerializer):
    """The card plus the curriculum. Structure sells the course; content does
    not appear until someone is entitled to it."""

    sections = PublicSectionSerializer(many=True, read_only=True)

    class Meta(PublicCourseSerializer.Meta):
        fields: ClassVar[list[str]] = [*PublicCourseSerializer.Meta.fields, "sections"]


class GatedLessonSerializer(serializers.ModelSerializer):
    """A lesson in full, including its content.

    The counterpart to ``PublicLessonSerializer``, which omits ``body``
    entirely. Two serializers rather than one with a conditional field, as
    ADR-008 §6 anticipated: the public one *cannot* render paid content
    because it has no such field, and this one is only reachable behind
    ``IsEntitledToLesson``. A single serializer branching on a flag would put
    the access decision inside the I/O layer, which invariant 2 forbids and
    which is one wrong branch away from serving everything.
    """

    course_slug = serializers.SlugField(source="course.slug", read_only=True)

    class Meta:
        model = Lesson
        fields: ClassVar[list[str]] = [
            "id",
            "course_slug",
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
        read_only_fields: ClassVar[list[str]] = fields
