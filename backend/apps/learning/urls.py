"""Learning routes.

Beside `lessons/{id}/` at the API root, because progress is a property of a
lesson *for the person asking* — there is no identifier for whose progress it
is, which is what makes another learner's unreachable rather than merely
forbidden.
"""

from django.urls import path

from apps.learning.views import LessonCompleteView, LessonProgressView

app_name = "learning"

urlpatterns = [
    path("lessons/<uuid:pk>/progress/", LessonProgressView.as_view(), name="progress"),
    path("lessons/<uuid:pk>/complete/", LessonCompleteView.as_view(), name="complete"),
]
