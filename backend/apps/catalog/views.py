"""The instructor course API.

HTTP concerns only (invariant 2). The publication rules live in
``services.py``; this decides status codes.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.models import Course
from apps.catalog.selectors import courses_for_instructor
from apps.catalog.serializers import CourseSerializer
from apps.catalog.services import InvalidTransition, NotPermitted, submit_for_review


@extend_schema(tags=["instructor"])
class InstructorCourseViewSet(viewsets.ModelViewSet):
    """CRUD over the courses you own.

    There is deliberately **no publish action here at all**. An instructor's
    only forward move is ``submit-for-review``; the route to PUBLISHED exists
    solely in Django Admin, for admins (ADR-007 §2). Absence is a stronger
    guarantee than a permission check on an endpoint that exists.
    """

    serializer_class = CourseSerializer
    lookup_field = "pk"

    def get_queryset(self):
        """Scoped to the caller. Every detail route resolves through this.

        This single filter is what turns "someone else's course" into a 404
        rather than a 403 for read, update *and* delete at once — there is no
        per-action check to forget.
        """
        # drf-spectacular introspects the view class with no authenticated
        # request, so it must get an empty queryset rather than an exception.
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return courses_for_instructor(user=self.request.user)

    def perform_create(self, serializer):
        # Ownership from the session. `instructor` is read-only on the
        # serializer, so a value in the body reaches nothing.
        serializer.save(instructor=self.request.user)

    @extend_schema(
        request=None,
        responses={
            200: CourseSerializer,
            404: OpenApiResponse(description="No such course of yours."),
            409: OpenApiResponse(description="Not in a state that can be submitted."),
        },
        summary="Submit a course for review",
    )
    @action(detail=True, methods=["post"], url_path="submit-for-review")
    def submit_for_review(self, request, pk=None):
        # get_object() runs the scoped queryset, so someone else's course is
        # already a 404 before this line.
        course = self.get_object()

        try:
            submit_for_review(course=course, by=request.user)
        except InvalidTransition:
            # 409, not 400: the request is well formed, the course is simply
            # not in a state this can leave (§6.3 — conflict).
            return Response(
                {"detail": "This course cannot be submitted from its current state."},
                status=status.HTTP_409_CONFLICT,
            )
        except NotPermitted:
            # Unreachable while the queryset is scoped, and kept as a second
            # line: if that filter is ever loosened, this refuses rather than
            # silently allowing the transition.
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(self.get_serializer(course).data)
