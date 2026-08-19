"""The learning surface — reading a lesson you are entitled to.

The first endpoint in the product that serves paid content, so it is the first
place the resolver is load-bearing rather than tested in isolation.

Two gates, in order, answering two different questions:

1. ``lessons_visible_to`` — does this lesson exist for you? An unpublished
   course is **404**, not 403, because a 403 confirms it exists (§6.3).
2. ``IsEntitledToLesson`` — may you read its contents? A refusal is **403**
   with a reason the interface can act on.

They are not interchangeable. Without the first, a paying subscriber reads
draft lessons: the resolver allows them on the SUBSCRIPTION_ACTIVE branch,
having never been asked about publication. Without the second, everyone reads
everything.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from apps.catalog.models import Lesson
from apps.catalog.selectors import lessons_visible_to
from apps.catalog.serializers import GatedLessonSerializer
from apps.entitlements.permissions import IsEntitledToLesson


@extend_schema(tags=["learning"])
class LessonViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """One lesson, in full, if you may see it.

    ``AllowAny`` is deliberate and is what makes preview lessons work for
    people with no account: the resolver's first branch allows a preview
    before it ever asks who is calling, and a blanket ``IsAuthenticated`` here
    would refuse them before that branch ran. Authentication is not the gate —
    entitlement is, and it decides for anonymous callers too.

    ``RetrieveModelMixin`` alone, **not** ``ReadOnlyModelViewSet``. That is a
    security control, not a style choice, and it was written the wrong way
    first: ``ReadOnlyModelViewSet`` also provides ``list``, and
    ``has_object_permission`` is never called for a list — so ``GET
    /lessons/`` returned every visible lesson, bodies included, to anonymous
    callers. The docstring claimed "retrieve only" while the class shipped the
    opposite.

    Object-level permissions cannot gate a collection. Anything that returns
    many lessons must either run the resolver per row or filter by a second
    access rule, and a second rule is the one that drifts (invariant 3). So
    there is no such route: curriculum comes from the public catalogue, which
    shows structure without content.
    """

    serializer_class = GatedLessonSerializer
    permission_classes = (AllowAny, IsEntitledToLesson)
    lookup_field = "pk"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lesson.objects.none()
        # select_related("course") comes from the selector, which the resolver
        # asks for — without it the ownership check costs an extra query on
        # every request for gated content.
        return lessons_visible_to(user=self.request.user)

    @extend_schema(
        responses={
            200: GatedLessonSerializer,
            403: OpenApiResponse(
                description=(
                    "Entitlement denied. Problem Details with a stable `reason` "
                    "and `cta` — see /problems/entitlement-denied."
                )
            ),
            404: OpenApiResponse(description="No such lesson, or not published."),
        },
        summary="Read a lesson",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
