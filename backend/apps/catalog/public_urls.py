"""Public catalogue routes.

Mounted at ``/api/v1/catalogue/``, separate from ``/api/v1/instructor/``, so
that the boundary between "anyone may read this" and "only the owner may" is
visible in the URL and can be reasoned about at the edge — a cache or WAF rule
can act on the prefix without knowing anything about the views behind it.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.catalog.public_views import (
    CourseSearchView,
    PublicCourseViewSet,
    PublicLanguageView,
)

app_name = "catalogue"

router = DefaultRouter()
router.register("courses", PublicCourseViewSet, basename="public-course")

urlpatterns = [
    path("search/", CourseSearchView.as_view(), name="course-search"),
    path("languages/", PublicLanguageView.as_view(), name="public-languages"),
    *router.urls,
]
