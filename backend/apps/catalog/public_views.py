"""The public catalogue — the only unauthenticated product surface.

Separate module from ``views.py`` on purpose. Everything in here is readable
by anyone on the internet, and that is easier to keep true when the permission
exemption is not interleaved with views that must stay scoped. A reviewer
reading this file knows every class in it is public; a reviewer reading
``views.py`` knows none of them are.
"""

from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Course
from apps.catalog.selectors import (
    languages_with_published_courses,
    published_course_detail,
    published_courses,
)
from apps.catalog.serializers import (
    LanguageSerializer,
    PublicCourseDetailSerializer,
    PublicCourseSerializer,
)


@extend_schema(tags=["catalogue"])
class PublicLanguageView(APIView):
    """Languages a visitor can actually browse.

    Unpaginated: this list is bounded by the number of languages taught, which
    is a handful, and a paginated filter control is a worse control.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_scope = "catalogue"

    @extend_schema(responses=LanguageSerializer(many=True), summary="Languages on offer")
    def get(self, request):
        languages = languages_with_published_courses()
        return Response(LanguageSerializer(languages, many=True).data)


@extend_schema(tags=["catalogue"])
class PublicCourseViewSet(viewsets.ReadOnlyModelViewSet):
    """Published courses, by slug.

    ``AllowAny`` is explicit and deliberate: DRF is configured to deny by
    default, so a public endpoint is an exemption, and an exemption is a thing
    to test rather than assume. ``authentication_classes = ()`` goes with it —
    the catalogue must behave identically for a signed-in visitor and an
    anonymous one, and skipping session lookup is also what keeps the response
    cacheable at the edge (invariant 15).

    Read-only because there is no public write anywhere in this product.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_scope = "catalogue"
    lookup_field = "slug"
    # Slugs, not UUIDs: these are the URLs the marketing pages are built on.
    lookup_value_regex = r"[-\w]+"

    def get_serializer_class(self):
        return PublicCourseDetailSerializer if self.action == "retrieve" else PublicCourseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return published_courses()

    @extend_schema(
        responses={
            200: PublicCourseDetailSerializer,
            404: OpenApiResponse(description="No published course with that slug."),
        },
        summary="One published course, with its curriculum",
    )
    def retrieve(self, request, slug=None):
        try:
            # Its own selector rather than get_object(): the detail page needs
            # the curriculum prefetched, and the list does not.
            course = published_course_detail(slug=slug)
        except Course.DoesNotExist as exc:
            # Abuse case 6. A draft and a slug that never existed answer
            # identically — anything else confirms the course is being worked
            # on, which is exactly what a competitor wants to know.
            raise Http404 from exc

        return Response(self.get_serializer(course).data)
