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

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, viewsets
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


@extend_schema(tags=["learning"])
class LessonBySlugView(generics.RetrieveAPIView):
    """The same lesson, addressed the way architecture.md §6.2 says it is.

    ``GET courses/{course_slug}/lessons/{lesson_slug}/``, specified at M0 and
    never built — M7 shipped ``/lessons/{id}/`` instead. **The schema was shaped
    for this route and has been waiting for it.** ADR-007 §1 put a redundant
    ``course`` foreign key on ``Lesson`` for exactly one stated reason:

        "§6.2 routes /courses/{slug}/lessons/{lesson_slug}/, which resolves to
        one lesson only if the slug is unique per course — and a constraint
        spanning two joins is not something Django can express."

    That constraint — ``lesson_slug_unique_per_course`` — is what makes this
    lookup return one row rather than an arbitrary one. Until now it guarded a
    URL nothing served.

    **Every gate is inherited, not restated.** The queryset is
    ``lessons_visible_to`` and the permission is ``IsEntitledToLesson``, both
    identical to ``LessonViewSet``. Invariant 3 has one resolver, and a second
    way to reach a lesson is exactly where a second access rule would grow.

    **Mounted at the API root rather than under ``/catalogue/``.**
    architecture.md's table lists this under "Catalogue", but that table
    predates the ``catalogue/`` prefix, which ``public_urls.py`` introduced so
    that "the boundary between 'anyone may read this' and 'only the owner may'
    is visible in the URL". This route serves gated content, so putting it
    behind that prefix would make the prefix lie.
    """

    serializer_class = GatedLessonSerializer
    # Identical to LessonViewSet, and for the identical reason: the resolver
    # allows a preview before it asks who is calling, so IsAuthenticated here
    # would refuse anonymous visitors before that branch ran.
    permission_classes = (AllowAny, IsEntitledToLesson)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lesson.objects.none()
        return lessons_visible_to(user=self.request.user)

    def get_object(self):
        """Resolve on two slugs, then apply the object permission.

        ``check_object_permissions`` is called explicitly because overriding
        ``get_object`` skips the base implementation that would have done it —
        and skipping it would serve gated bodies to anyone who could guess a
        slug. The base class cannot express a two-field lookup, so the call has
        to be made by hand, which is precisely the kind of thing a test has to
        prove rather than a docstring assert.
        """
        lesson = get_object_or_404(
            self.get_queryset(),
            course__slug=self.kwargs["course_slug"],
            slug=self.kwargs["lesson_slug"],
        )
        self.check_object_permissions(self.request, lesson)
        return lesson

    @extend_schema(
        responses={
            200: GatedLessonSerializer,
            403: OpenApiResponse(
                description=(
                    "Entitlement denied. Problem Details with a stable `reason` "
                    "and `cta` — see /problems/entitlement-denied."
                )
            ),
            404: OpenApiResponse(description="No such lesson in that course, or not published."),
        },
        summary="Read a lesson, addressed by course and lesson slug",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
