"""Learning routes — content served to a learner.

Its own prefix, separate from `/instructor/` and `/catalogue/`, because the
three have different access rules and a reviewer should be able to tell which
is which from the path. `/lessons/{id}/` matches architecture.md section 6.2,
where `lessons/{id}/playback-token/` hangs off the same resource in M5.
"""

from rest_framework.routers import DefaultRouter

from apps.catalog.learning_views import LessonViewSet

app_name = "learning"

router = DefaultRouter()
router.register("lessons", LessonViewSet, basename="lesson")

urlpatterns = router.urls
