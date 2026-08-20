"""Media routes (architecture.md section 6.2).

Mounted at the API root rather than under an `/instructor/` prefix, because
`media-assets/{id}/complete/` is addressed by asset and the upload route by
lesson — neither is a sub-resource of a course. Ownership is decided by the
service layer, not by where the path sits.
"""

from django.urls import path

from apps.media_assets.views import LessonUploadUrlView, MediaAssetCompleteView

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
]
