"""Instructor catalogue routes (architecture.md section 6.2)."""

from rest_framework.routers import DefaultRouter

from apps.catalog.views import InstructorCourseViewSet

app_name = "catalog"

router = DefaultRouter()
router.register("courses", InstructorCourseViewSet, basename="instructor-course")

urlpatterns = router.urls
