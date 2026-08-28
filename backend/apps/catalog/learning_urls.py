"""Learning routes — content served to a learner.

Its own prefix, separate from `/instructor/` and `/catalogue/`, because the
three have different access rules and a reviewer should be able to tell which
is which from the path. `/lessons/{id}/` matches architecture.md section 6.2,
where `lessons/{id}/playback-token/` hangs off the same resource in M5.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.catalog.learning_views import LessonBySlugView, LessonViewSet

# "lesson-content", not "learning": apps.learning owns that namespace, and two
# includes claiming one namespace is a Django warning today and an unreversible
# URL the moment anything calls reverse() — the same shape as M6's colliding
# provider namespaces, in the URL conf.
app_name = "lesson-content"

router = DefaultRouter()
router.register("lessons", LessonViewSet, basename="lesson")

urlpatterns = [
    # architecture.md §6.2, specified at M0 and built at M16 T3. The same
    # lesson as `lessons/{id}/` above, addressed the way a person would write
    # it — which is what `Lesson`'s redundant `course` foreign key and the
    # `lesson_slug_unique_per_course` constraint were put there to allow
    # (ADR-007 §1).
    #
    # Two ways to reach one resource, sharing one view's queryset and one
    # permission class. That sharing is the point: invariant 3 has one
    # resolver, and a second route is exactly where a second access rule would
    # grow.
    path(
        "courses/<slug:course_slug>/lessons/<slug:lesson_slug>/",
        LessonBySlugView.as_view(),
        name="lesson-by-slug",
    ),
    *router.urls,
]
