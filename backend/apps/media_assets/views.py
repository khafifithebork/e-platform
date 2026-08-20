"""Upload endpoints. HTTP concerns only (invariant 2).

Two routes, both scoped to whoever may manage the lesson. Someone else's
lesson is a **404**, never a 403: a 403 confirms the lesson exists, which is
what §6.3 forbids.
"""

from dataclasses import asdict

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Lesson
from apps.catalog.selectors import lessons_visible_to
from apps.media_assets.models import MediaAsset
from apps.media_assets.providers.storage import UnsupportedContentType, object_storage
from apps.media_assets.serializers import (
    MediaAssetSerializer,
    PlaybackTokenSerializer,
    UploadRequestSerializer,
    UploadTicketSerializer,
)
from apps.media_assets.services import (
    NotPlayable,
    NotYours,
    UploadNotAllowed,
    UploadVerificationFailed,
    complete_upload,
    issue_playback_token,
    request_upload,
)


@extend_schema(tags=["media"])
class LessonUploadUrlView(APIView):
    """Authorise one upload for one lesson.

    Throttled on its own scope: each call signs a URL that can write to our
    bucket, so an unthrottled version is a way to mint write grants without
    ever uploading through us.
    """

    throttle_scope = "media_upload"

    @extend_schema(
        request=UploadRequestSerializer,
        responses={
            201: UploadTicketSerializer,
            400: OpenApiResponse(description="Unsupported content type."),
            404: OpenApiResponse(description="No such lesson of yours."),
            409: OpenApiResponse(description="The current asset cannot be replaced."),
        },
        summary="Request a presigned upload URL",
    )
    def post(self, request, pk):
        payload = UploadRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        lesson = get_object_or_404(Lesson.objects.select_related("course"), pk=pk)

        try:
            asset, upload = request_upload(
                lesson=lesson,
                by=request.user,
                content_type=payload.validated_data["content_type"],
                storage=object_storage(),
            )
        except NotYours:
            # Distinct from UploadNotAllowed so the two cannot be confused at
            # the boundary: not-yours must look exactly like does-not-exist,
            # while a state conflict is a real 409 the caller can act on.
            return Response(status=status.HTTP_404_NOT_FOUND)
        except UploadNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except UnsupportedContentType as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            UploadTicketSerializer({"asset": asset, "upload": asdict(upload)}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["media"])
class MediaAssetCompleteView(APIView):
    """Confirm an upload landed, and verify it before believing it."""

    throttle_scope = "media_upload"

    @extend_schema(
        request=None,
        responses={
            200: MediaAssetSerializer,
            404: OpenApiResponse(description="No such asset of yours."),
            409: OpenApiResponse(description="Not awaiting an upload."),
            422: OpenApiResponse(
                description="Nothing uploaded, too large, or not the declared type."
            ),
        },
        summary="Confirm an upload",
    )
    def post(self, request, pk):
        asset = get_object_or_404(MediaAsset.objects.select_related("lesson__course"), pk=pk)

        try:
            complete_upload(asset=asset, by=request.user, storage=object_storage())
        except NotYours:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except UploadNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except UploadVerificationFailed as exc:
            # 422, not 400: the request is well formed and the *object* is
            # what is wrong, which is §6.3's "semantically invalid".
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response(MediaAssetSerializer(asset).data)


@extend_schema(tags=["media"])
class LessonPlaybackTokenView(APIView):
    """Permission to play one lesson, if the resolver allows it.

    ``AllowAny``, deliberately, and it is the same reasoning as the gated
    lesson endpoint: a preview lesson is playable by someone with no account,
    and a blanket ``IsAuthenticated`` here would refuse them before the
    resolver's first branch ran. **Entitlement is the gate, not
    authentication** — and it decides for anonymous callers too.

    Two gates, as everywhere in this codebase: ``lessons_visible_to`` answers
    whether the lesson exists for you (404 if not), then the resolver answers
    whether you may see it (403 with a reason). The resolver knows about
    subscriptions, not publication, so without the first a subscriber could
    play an unpublished draft.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "playback_token"

    @extend_schema(
        request=None,
        responses={
            200: PlaybackTokenSerializer,
            403: OpenApiResponse(description="Entitlement denied, with a reason and a cta."),
            404: OpenApiResponse(description="No such lesson."),
            409: OpenApiResponse(description="The media is not ready to play yet."),
        },
        summary="Mint a playback token",
    )
    def post(self, request, pk):
        lesson = get_object_or_404(lessons_visible_to(user=request.user), pk=pk)

        try:
            token = issue_playback_token(user=request.user, lesson=lesson)
        except NotPlayable as exc:
            # 409, not 403: they may watch it, there is simply nothing
            # transcoded yet. A 403 would send a paying subscriber to the
            # upgrade page for a problem that is ours.
            return Response(
                {"detail": f"Media is not ready ({exc}).", "status": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        # EntitlementDenied is deliberately not caught: it is an APIException
        # carrying its own status, type, reason and cta, and the Problem
        # Details handler renders it (ADR-004). Catching it here to rebuild a
        # response by hand is how the reason gets lost.
        return Response(PlaybackTokenSerializer(token).data)
