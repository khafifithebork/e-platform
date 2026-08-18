"""The instructor course API.

HTTP concerns only (invariant 2). The publication rules live in
``services.py``; this decides status codes.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.catalog.models import Course, CourseReviewEvent, Lesson, Section
from apps.catalog.selectors import (
    courses_for_instructor,
    lessons_for_course,
    review_events_for_course,
    sections_for_course,
)
from apps.catalog.serializers import (
    CourseReviewEventSerializer,
    CourseSerializer,
    LessonReorderSerializer,
    LessonSerializer,
    ReorderSerializer,
    SectionSerializer,
)
from apps.catalog.services import (
    InvalidReorder,
    InvalidTransition,
    NotPermitted,
    reorder_lessons,
    reorder_sections,
    submit_for_review,
)


@extend_schema(tags=["instructor"])
class InstructorCourseViewSet(viewsets.ModelViewSet):
    """CRUD over the courses you own.

    There is deliberately **no publish action here at all**. An instructor's
    only forward move is ``submit-for-review``; the route to PUBLISHED exists
    solely in Django Admin, for admins (ADR-007 §2). Absence is a stronger
    guarantee than a permission check on an endpoint that exists.
    """

    serializer_class = CourseSerializer
    lookup_field = "pk"

    def get_queryset(self):
        """Scoped to the caller. Every detail route resolves through this.

        This single filter is what turns "someone else's course" into a 404
        rather than a 403 for read, update *and* delete at once — there is no
        per-action check to forget.
        """
        # drf-spectacular introspects the view class with no authenticated
        # request, so it must get an empty queryset rather than an exception.
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return courses_for_instructor(user=self.request.user)

    def perform_create(self, serializer):
        # Ownership from the session. `instructor` is read-only on the
        # serializer, so a value in the body reaches nothing.
        serializer.save(instructor=self.request.user)

    @extend_schema(
        request=None,
        responses={
            200: CourseSerializer,
            404: OpenApiResponse(description="No such course of yours."),
            409: OpenApiResponse(description="Not in a state that can be submitted."),
        },
        summary="Submit a course for review",
    )
    @action(detail=True, methods=["post"], url_path="submit-for-review")
    def submit_for_review(self, request, pk=None):
        # get_object() runs the scoped queryset, so someone else's course is
        # already a 404 before this line.
        course = self.get_object()

        try:
            submit_for_review(course=course, by=request.user)
        except InvalidTransition:
            # 409, not 400: the request is well formed, the course is simply
            # not in a state this can leave (§6.3 — conflict).
            return Response(
                {"detail": "This course cannot be submitted from its current state."},
                status=status.HTTP_409_CONFLICT,
            )
        except NotPermitted:
            # Unreachable while the queryset is scoped, and kept as a second
            # line: if that filter is ever loosened, this refuses rather than
            # silently allowing the transition.
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(self.get_serializer(course).data)


class _CourseScopedMixin:
    """Ownership resolution for anything that hangs off a course.

    Every route resolves the parent course through ``courses_for_instructor``,
    so a course belonging to somebody else is a 404 before a section or lesson
    is ever looked at. Nothing using this mixin repeats the ownership check,
    and nothing using it may skip one.

    Deliberately a mixin and not a ``ModelViewSet`` subclass. It was the
    latter, and ``InstructorReviewEventViewSet(_CourseScopedViewSet,
    ReadOnlyModelViewSet)`` then resolved ``CreateModelMixin`` from the *base*
    first: the read-only viewset was shadowed and the trail accepted POSTs
    while the class name said it could not. A mixin carries no verbs, so each
    viewset's own base decides what it accepts and cannot be overruled from
    here.
    """

    def _course(self) -> Course:
        cached = getattr(self, "_course_cache", None)
        if cached is None:
            # DRF's get_object_or_404, not Django's: it turns a malformed UUID
            # into a 404 instead of letting a ValidationError become a 500.
            cached = get_object_or_404(
                courses_for_instructor(user=self.request.user),
                pk=self.kwargs["course_pk"],
            )
            self._course_cache = cached
        return cached


@extend_schema(tags=["instructor"])
class InstructorSectionViewSet(_CourseScopedMixin, viewsets.ModelViewSet):
    """Sections of one of your courses."""

    serializer_class = SectionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Section.objects.none()
        return sections_for_course(course=self._course())

    def perform_create(self, serializer):
        serializer.save(course=self._course())

    @extend_schema(
        request=ReorderSerializer,
        responses={
            200: SectionSerializer(many=True),
            400: OpenApiResponse(description="The order did not name exactly these sections."),
            404: OpenApiResponse(description="No such course of yours."),
        },
        summary="Reorder a course's sections",
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request, course_pk=None):
        course = self._course()
        payload = ReorderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            reorder_sections(course=course, ordered_ids=payload.validated_data["order"])
        except InvalidReorder as exc:
            # 400, not 409: the payload itself is wrong, and nothing about the
            # course's state would make this same request succeed later.
            raise ValidationError({"order": [str(exc)]}) from exc

        return Response(self.get_serializer(self.get_queryset(), many=True).data)


@extend_schema(tags=["instructor"])
class InstructorLessonViewSet(_CourseScopedMixin, viewsets.ModelViewSet):
    """Lessons of one of your courses."""

    serializer_class = LessonSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lesson.objects.none()
        return lessons_for_course(course=self._course())

    def get_serializer(self, *args, **kwargs):
        """Narrow ``section`` to this course.

        Both the lesson and the section are individually valid rows, so no
        database constraint can reject the pairing; the only place that knows
        they must share a course is here, where the URL names it. Narrowing the
        related queryset makes DRF answer 400 "does not exist" — the same reply
        a wholly invented id gets, which is what §6.3 wants: no confirmation
        that the other course's section is real.
        """
        serializer = super().get_serializer(*args, **kwargs)
        target = getattr(serializer, "child", serializer)
        field = target.fields.get("section")
        if field is not None and not getattr(self, "swagger_fake_view", False):
            field.queryset = Section.objects.filter(course=self._course())
        return serializer

    def perform_create(self, serializer):
        # `course` comes from the URL and the section is already narrowed to
        # it, so the two cannot disagree.
        serializer.save(course=self._course())

    @extend_schema(
        request=LessonReorderSerializer,
        responses={
            200: LessonSerializer(many=True),
            400: OpenApiResponse(description="The order did not name exactly these lessons."),
            404: OpenApiResponse(description="No such course or section of yours."),
        },
        summary="Reorder one section's lessons",
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request, course_pk=None):
        course = self._course()
        payload = LessonReorderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        # Scoped to the course from the URL, so a section of somebody else's
        # course is a 404 rather than a reorder of their lessons.
        section = get_object_or_404(
            Section.objects.filter(course=course), pk=payload.validated_data["section"]
        )

        try:
            reorder_lessons(section=section, ordered_ids=payload.validated_data["order"])
        except InvalidReorder as exc:
            raise ValidationError({"order": [str(exc)]}) from exc

        return Response(self.get_serializer(self.get_queryset(), many=True).data)


@extend_schema(tags=["instructor"])
class InstructorReviewEventViewSet(_CourseScopedMixin, viewsets.ReadOnlyModelViewSet):
    """The review history of one of your courses.

    ``ReadOnlyModelViewSet``, and that is the security control rather than a
    convenience: a writable trail would let an instructor POST themselves an
    APPROVED event. Nothing downstream reads this table to decide access —
    publication runs through the state machine in ``services.py`` — so a
    forgery would mislead a human rather than grant anything, which is still a
    bug worth closing at the route.
    """

    serializer_class = CourseReviewEventSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CourseReviewEvent.objects.none()
        return review_events_for_course(course=self._course())
