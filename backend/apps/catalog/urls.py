"""Instructor catalogue routes (architecture.md section 6.2).

Sections and lessons are nested under their course rather than exposed flat.
That is a security choice, not an aesthetic one: with the course in the path,
every nested route resolves ownership through the same scoped queryset the
course routes use, and there is no id-only endpoint where forgetting a filter
would expose someone else's curriculum.

Nesting is done with a regex prefix on the stock router. `drf-nested-routers`
would read better but is a new dependency, which CLAUDE.md section 5 requires
approval for, and two registrations do not justify asking.
"""

from rest_framework.routers import DefaultRouter

from apps.catalog.views import (
    InstructorCourseViewSet,
    InstructorLessonViewSet,
    InstructorReviewEventViewSet,
    InstructorSectionViewSet,
)

app_name = "catalog"

# `[^/.]+` rather than a UUID pattern so that a malformed id reaches the view
# and answers 404, instead of missing the route and answering 404 for a
# different reason that no test would distinguish.
COURSE = r"courses/(?P<course_pk>[^/.]+)"

router = DefaultRouter()
router.register("courses", InstructorCourseViewSet, basename="instructor-course")
router.register(f"{COURSE}/sections", InstructorSectionViewSet, basename="instructor-section")
router.register(f"{COURSE}/lessons", InstructorLessonViewSet, basename="instructor-lesson")
router.register(
    f"{COURSE}/review-events", InstructorReviewEventViewSet, basename="instructor-review-event"
)

urlpatterns = router.urls
