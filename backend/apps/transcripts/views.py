"""Transcript review endpoints. HTTP concerns only (invariant 2).

Someone else's transcript is a **404**, never a 403: a 403 confirms it exists,
which §6.3 forbids. Ownership is checked in the view rather than by a queryset
filter because a transcript and a segment are each addressed by their own id —
architecture.md §4.4 calls exactly that the commonest IDOR in DRF codebases.
"""

from typing import ClassVar

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotModified
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.selectors import lessons_visible_to
from apps.entitlements.exceptions import EntitlementDenied
from apps.entitlements.resolver import resolve_access
from apps.transcripts.models import Transcript, TranscriptSegment
from apps.transcripts.rendering import render_vtt
from apps.transcripts.selectors import approved_transcript_for, transcript_for_review
from apps.transcripts.serializers import (
    SegmentEditSerializer,
    SegmentSerializer,
    TranscriptSerializer,
)
from apps.transcripts.services import (
    InvalidSpan,
    InvalidTransition,
    NotEditable,
    NothingToApprove,
    NotYours,
    approve,
    edit_segment,
    may_review,
    reopen,
    start_review,
)


@extend_schema(tags=["transcripts"])
class TranscriptDetailView(APIView):
    """The review screen's data: a transcript and every cue in it."""

    throttle_scope = "user"

    @extend_schema(
        responses={
            200: TranscriptSerializer,
            404: OpenApiResponse(description="No such transcript of yours."),
        },
        summary="Read a transcript for review",
    )
    def get(self, request, pk):
        transcript = transcript_for_review(pk=pk)
        if transcript is None or not may_review(transcript=transcript, user=request.user):
            # One branch for both, deliberately: "does not exist" and "not
            # yours" must be indistinguishable from outside.
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(TranscriptSerializer(transcript).data)


@extend_schema(tags=["transcripts"])
class SegmentEditView(APIView):
    """Correct one cue."""

    throttle_scope = "user"

    @extend_schema(
        request=SegmentEditSerializer,
        responses={
            200: SegmentSerializer,
            400: OpenApiResponse(description="Nothing to change, or an invalid span."),
            404: OpenApiResponse(description="No such segment of yours."),
            409: OpenApiResponse(description="The transcript cannot be edited yet."),
        },
        summary="Edit a transcript segment",
    )
    def patch(self, request, pk):
        payload = SegmentEditSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        segment = get_object_or_404(
            TranscriptSegment.objects.select_related("transcript__media_asset__lesson__course"),
            pk=pk,
        )

        try:
            edit_segment(segment=segment, by=request.user, **payload.validated_data)
        except NotYours:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except NotEditable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InvalidSpan as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SegmentSerializer(segment).data)


@extend_schema(tags=["transcripts"])
class TranscriptReviewView(APIView):
    """The review transitions: open, approve, reopen.

    One view with an action in the path rather than a writable ``status``
    field. A writable status would be a second route to APPROVED that records
    no reviewer and no time — the same argument ADR-007 §2 makes for course
    publication, and here it also decides whether a learner is served
    subtitles at all.
    """

    throttle_scope = "user"

    ACTIONS: ClassVar[dict] = {
        "start-review": start_review,
        "approve": approve,
        "reopen": reopen,
    }

    @extend_schema(
        request=None,
        responses={
            200: TranscriptSerializer,
            404: OpenApiResponse(description="No such transcript of yours."),
            409: OpenApiResponse(description="Not a move this transcript can make."),
            422: OpenApiResponse(description="Nothing to approve."),
        },
        summary="Move a transcript through review",
    )
    def post(self, request, pk, action):
        transcript = get_object_or_404(
            Transcript.objects.select_related("media_asset__lesson__course"), pk=pk
        )

        try:
            self.ACTIONS[action](transcript=transcript, by=request.user)
        except NotYours:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except InvalidTransition as exc:
            # 409, not 400: the request is well formed and the transcript is
            # simply not in a state this can leave (§6.3 — conflict).
            return Response({"detail": f"Cannot do that: {exc}."}, status=status.HTTP_409_CONFLICT)
        except NothingToApprove as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response(TranscriptSerializer(transcript_for_review(pk=pk)).data)


@extend_schema(tags=["learning"])
class LessonTranscriptView(APIView):
    """Subtitles for a lesson, as WebVTT.

    Two gates, the same pair as playback: ``lessons_visible_to`` answers
    whether the lesson exists for you (404), then the entitlement resolver
    answers whether you may read it (403 with a reason). Subtitles are the
    lesson's content in written form, so anything looser here would hand over
    in text what the playback token is guarding in video.

    ``AllowAny``, because a preview lesson's subtitles are as public as its
    video — the resolver's first branch decides that, and a blanket
    authentication check would refuse them before it ran.

    Rendered on demand and cached, never stored (invariant 13). The cache key
    carries the transcript's ``updated_at``, so an edit produces a different
    key rather than needing a purge; the ETag carries the same version, so a
    returning learner revalidates with a 304 instead of re-downloading.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "catalogue"

    @extend_schema(
        responses={
            200: OpenApiResponse(description="A WebVTT file."),
            304: OpenApiResponse(description="Unchanged since the ETag you hold."),
            403: OpenApiResponse(description="Entitlement denied, with a reason."),
            404: OpenApiResponse(description="No lesson, or no approved transcript."),
        },
        summary="Subtitles for a lesson",
    )
    def get(self, request, pk):
        lesson = get_object_or_404(lessons_visible_to(user=request.user), pk=pk)

        decision = resolve_access(user=request.user, lesson=lesson)
        if not decision.allowed:
            # Raised, not returned: EntitlementDenied carries its own status,
            # type, reason and cta, and the Problem Details handler renders it
            # (ADR-004). Rebuilding that here is how the reason gets lost.
            raise EntitlementDenied(decision)

        transcript = approved_transcript_for(lesson=lesson)
        if transcript is None:
            # 404 rather than 204: there is no subtitle resource here. An
            # unapproved transcript is indistinguishable from none at all,
            # which is deliberate — a learner has no business knowing that
            # unreviewed words exist.
            return Response(status=status.HTTP_404_NOT_FOUND)

        version = f'"{transcript.pk}:{transcript.updated_at.timestamp()}"'
        if request.headers.get("If-None-Match") == version:
            return HttpResponseNotModified()

        body = cache.get_or_set(
            f"vtt:{version}",
            lambda: render_vtt(transcript.segments.all()),
            timeout=settings.TRANSCRIPT_VTT_CACHE_SECONDS,
        )

        response = HttpResponse(body, content_type="text/vtt; charset=utf-8")
        response["ETag"] = version
        # Private: subtitles are gated content, and a shared cache holding
        # them would serve one learner's entitlement to the next request.
        response["Cache-Control"] = "private, max-age=0, must-revalidate"
        return response
