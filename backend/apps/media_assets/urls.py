"""Media routes (architecture.md section 6.2).

Mounted at the API root rather than under an `/instructor/` prefix, because
`media-assets/{id}/complete/` is addressed by asset and the upload route by
lesson — neither is a sub-resource of a course. Ownership is decided by the
service layer, not by where the path sits.
"""

from django.urls import path

from apps.media_assets.views import (
    LessonPlaybackTokenView,
    LessonUploadUrlView,
    MediaAssetCompleteView,
)
from apps.media_assets.webhooks import VideoWebhookView

app_name = "media"

urlpatterns = [
    path(
        "lessons/<uuid:pk>/media/upload-url/",
        LessonUploadUrlView.as_view(),
        name="upload-url",
    ),
    path(
        "media-assets/<uuid:pk>/complete/",
        MediaAssetCompleteView.as_view(),
        name="complete",
    ),
    path(
        "lessons/<uuid:pk>/playback-token/",
        LessonPlaybackTokenView.as_view(),
        name="playback-token",
    ),
    # Called by the provider, not a browser. Unauthenticated: the signature
    # is the authentication (invariant 8).
    path("webhooks/video/", VideoWebhookView.as_view(), name="video-webhook"),
]
