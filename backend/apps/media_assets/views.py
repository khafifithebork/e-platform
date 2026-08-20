"""Upload endpoints. HTTP concerns only (invariant 2).

Two routes, both scoped to whoever may manage the lesson. Someone else's
lesson is a **404**, never a 403: a 403 confirms the lesson exists, which is
what §6.3 forbids.
"""

from dataclasses import asdict

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Lesson
from apps.media_assets.models import MediaAsset
from apps.media_assets.providers.storage import UnsupportedContentType, object_storage
from apps.media_assets.serializers import (
    MediaAssetSerializer,
    UploadRequestSerializer,
    UploadTicketSerializer,
)
from apps.media_assets.services import (
    NotYours,
    UploadNotAllowed,
    UploadVerificationFailed,
    complete_upload,
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
