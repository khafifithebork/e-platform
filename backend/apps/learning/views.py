"""Progress endpoints. HTTP concerns only (invariant 2).

**There is no identifier for whose progress this is.** Every route reads and
writes ``request.user``'s own row, so abuse case 4 — reaching another
learner's progress — is not defended against, it is unreachable.
architecture.md §4.4 calls fetching by a client-supplied identifier the
commonest IDOR in DRF codebases; the fix here is to accept none.

Entitlement is decided in the service beside the write, so ``EntitlementDenied``
is deliberately not caught: it carries its own status, type, reason and cta,
and the Problem Details handler renders it (ADR-004).
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.selectors import lessons_visible_to
from apps.learning.models import LessonProgress
from apps.learning.selectors import courses_in_progress
from apps.learning.serializers import (
    EnrollmentSerializer,
    HeartbeatSerializer,
    LessonProgressSerializer,
)
from apps.learning.services import Heartbeat, mark_complete, record_progress


@extend_schema(tags=["learning"])
class LessonProgressView(APIView):
    """Read or report progress through one lesson."""

    # §10 M7 names "a progress write per second" as this milestone's mistake.
    # A player beats every ten to fifteen seconds, so this is generous enough
    # for several lessons open at once and tight enough that a client looping
    # on every timeupdate event is stopped rather than served.
    throttle_scope = "progress"

    @extend_schema(
        responses={
            200: LessonProgressSerializer,
            204: OpenApiResponse(description="Never started."),
            404: OpenApiResponse(description="No such lesson."),
        },
        summary="Where a learner got to",
    )
    def get(self, request, pk):
        lesson = get_object_or_404(lessons_visible_to(user=request.user), pk=pk)

        progress = LessonProgress.objects.filter(user=request.user, lesson=lesson).first()
        if progress is None:
            # 204 rather than 404: the lesson exists and the learner simply
            # has not started it, which a player needs to tell apart from a
            # lesson that is not there.
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(LessonProgressSerializer(progress).data)

    @extend_schema(
        request=HeartbeatSerializer,
        responses={
            200: LessonProgressSerializer,
            400: OpenApiResponse(description="Malformed heartbeat."),
            403: OpenApiResponse(description="Entitlement denied, with a reason."),
            404: OpenApiResponse(description="No such lesson."),
        },
        summary="Report a heartbeat",
    )
    def put(self, request, pk):
        payload = HeartbeatSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        lesson = get_object_or_404(lessons_visible_to(user=request.user), pk=pk)

        progress = record_progress(
            user=request.user,
            lesson=lesson,
            heartbeat=Heartbeat(**payload.validated_data),
        )
        return Response(LessonProgressSerializer(progress).data)


@extend_schema(tags=["learning"])
class LessonCompleteView(APIView):
    """Let a learner say they are done with a lesson."""

    throttle_scope = "progress"

    @extend_schema(
        request=None,
        responses={
            200: LessonProgressSerializer,
            403: OpenApiResponse(description="Entitlement denied, with a reason."),
            404: OpenApiResponse(description="No such lesson."),
        },
        summary="Mark a lesson complete",
    )
    def post(self, request, pk):
        lesson = get_object_or_404(lessons_visible_to(user=request.user), pk=pk)

        progress = mark_complete(user=request.user, lesson=lesson)
        return Response(LessonProgressSerializer(progress).data)


@extend_schema(tags=["learning"], summary="Courses this learner has started")
class MyCoursesView(ListAPIView):
    """ "My courses" — what to come back to.

    Under ``/me/`` rather than ``/learners/{id}/courses/`` for the reason the
    progress routes carry no identifier either: the only answerable question is
    about the caller, so there is nothing to tamper with.

    No entitlement check. Someone whose subscription lapsed still sees what
    they were partway through — that list is what asks them to come back, and
    an enrolment grants nothing on its own (ADR-016 §1). The lessons behind it
    are gated where they always were, at playback.
    """

    serializer_class = EnrollmentSerializer

    def get_queryset(self):
        return courses_in_progress(user=self.request.user)
