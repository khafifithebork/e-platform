"""Transcript review endpoints. HTTP concerns only (invariant 2).

Someone else's transcript is a **404**, never a 403: a 403 confirms it exists,
which §6.3 forbids. Ownership is checked in the view rather than by a queryset
filter because a transcript and a segment are each addressed by their own id —
architecture.md §4.4 calls exactly that the commonest IDOR in DRF codebases.
"""

from typing import ClassVar

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transcripts.models import Transcript, TranscriptSegment
from apps.transcripts.selectors import transcript_for_review
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
