"""The public catalogue — the only unauthenticated product surface.

Separate module from ``views.py`` on purpose. Everything in here is readable
by anyone on the internet, and that is easier to keep true when the permission
exemption is not interleaved with views that must stay scoped. A reviewer
reading this file knows every class in it is public; a reviewer reading
``views.py`` knows none of them are.
"""

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Course
from apps.catalog.selectors import (
    MAX_QUERY_LENGTH,
    SEARCH_LIMIT,
    filtered_published_courses,
    languages_with_published_courses,
    published_course_detail,
    search_published_courses,
)
from apps.catalog.serializers import (
    CourseFilterSerializer,
    CourseSearchResultsSerializer,
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

    @extend_schema(
        parameters=[
            OpenApiParameter(name="language", description="ISO 639 code, e.g. `es`.", type=str),
            OpenApiParameter(name="level", description="CEFR level, e.g. `A1`.", type=str),
            OpenApiParameter(name="skill_area", description="One skill tag.", type=str),
        ],
        responses={
            200: PublicCourseSerializer(many=True),
            400: OpenApiResponse(description="An unrecognised filter value."),
        },
        summary="Browse published courses",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        return PublicCourseDetailSerializer if self.action == "retrieve" else PublicCourseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()

        # Validated before it narrows anything. An unrecognised value is a 400
        # from `raise_exception=True`, never a filter quietly dropped — a
        # dropped filter returns the whole catalogue and reads to the caller
        # exactly like one that matched everything.
        filters = CourseFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)

        return filtered_published_courses(**filters.validated_data)

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


@extend_schema(tags=["catalogue"])
class CourseSearchView(APIView):
    """Search the published catalogue.

    Its own endpoint rather than a `?q=` on the course list, because the two
    have incompatible shapes: the list is cursor-paginated by publication date,
    and results here are ranked and capped (ADR-020 §4). Bolting a query
    parameter onto the list would mean one endpoint whose pagination silently
    changes meaning depending on whether a parameter is present.

    Its own throttle scope for the same reason it is capped: a ranked query
    over a GIN index is the most expensive thing an anonymous visitor can ask
    this service to do, and the catalogue scope is sized for browsing.

    `AllowAny` with no authentication, matching the rest of this module — a
    signed-in visitor and an anonymous one must get identical results, because
    search reads only published rows and there is nothing to personalise.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_scope = "search"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="q",
                description=f"Search terms. Truncated at {MAX_QUERY_LENGTH} characters.",
                required=True,
                type=str,
            )
        ],
        responses={200: CourseSearchResultsSerializer},
        summary="Search published courses",
    )
    def get(self, request):
        courses = search_published_courses(query=request.query_params.get("q", ""))

        return Response(
            CourseSearchResultsSerializer(
                {
                    "results": courses,
                    "count": len(courses),
                    "limit": SEARCH_LIMIT,
                    "truncated": len(courses) == SEARCH_LIMIT,
                }
            ).data
        )
