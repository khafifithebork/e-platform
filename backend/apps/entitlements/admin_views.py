"""Why is this person's access wrong?

architecture.md §6.2 specifies ``users/{id}/diagnostics/`` carrying
"subscription state, event log, entitlement trace, override history". §5.2
gives the reason: a mutable ``status`` answers what is true now and cannot
answer why somebody's access is wrong, which is the actual support ticket six
weeks later.

The endpoint returns the resolver's own decision rather than describing the
rules in prose. Anything that explained entitlement in its own words would be
a second implementation of it, drifting from the first (invariant 3).
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.entitlements.permissions import IsAdministrator
from apps.entitlements.resolver import resolve_account_access
from apps.entitlements.selectors import diagnostics_for
from apps.entitlements.serializers import (
    AccessOverrideGrantSerializer,
    AccessOverrideSerializer,
    UserDiagnosticsSerializer,
)
from apps.entitlements.services import InvalidOverride, grant_access_override


@extend_schema(tags=["admin"])
class UserDiagnosticsView(APIView):
    """Everything known about one person's entitlement.

    Administrators only — ``role == ADMIN``, not ``is_staff`` (M3's
    distinction). This reads another person's billing history, which is the
    most sensitive read in the product outside the admin site itself.

    Deliberately read-only. Support diagnosing a problem should not be able to
    fix it by editing rows here; changing access means granting an override,
    which is recorded with a grantor and a reason.
    """

    permission_classes = (IsAdministrator,)
    throttle_scope = "user"

    @extend_schema(
        responses={
            200: UserDiagnosticsSerializer,
            403: OpenApiResponse(description="Not an administrator."),
            404: OpenApiResponse(description="No such user."),
        },
        summary="Diagnose a user's entitlement",
    )
    def get(self, request, pk):
        user = get_object_or_404(User.objects.all(), pk=pk)
        subscriptions, events, overrides = diagnostics_for(user=user)

        # The resolver's answer, not a description of it. If this disagreed
        # with what the person experiences, the diagnosis would be worse than
        # useless — it would send support looking in the wrong place.
        decision = resolve_account_access(user=user)

        return Response(
            UserDiagnosticsSerializer(
                {
                    "user": user,
                    "access": {
                        "allowed": decision.allowed,
                        "reason": str(decision.reason),
                        "cta": decision.cta,
                    },
                    "subscriptions": subscriptions,
                    "events": events,
                    "overrides": overrides,
                }
            ).data
        )


@extend_schema(tags=["admin"])
class UserAccessOverrideView(APIView):
    """Grant one person access the billing system does not.

    The write half of diagnostics. §10 M10's deliverable is that an admin can
    resolve any access complaint **without touching the database**, and until
    now an override could only be created by hand in Postgres — which is the
    same as saying the deliverable was unmet.

    Administrators only, `role == ADMIN`. Not `is_staff`: this hands out paid
    content, and the day somebody is given staff to fix a typo must not be the
    day they can give the catalogue away.

    Audited by the service, in the grant's own transaction. Not here — a view
    that audits records what it asked for rather than what happened.
    """

    permission_classes = (IsAdministrator,)
    throttle_scope = "user"

    @extend_schema(
        request=AccessOverrideGrantSerializer,
        responses={
            201: AccessOverrideSerializer,
            400: OpenApiResponse(description="No reason, or a duration out of range."),
            403: OpenApiResponse(description="Not an administrator."),
            404: OpenApiResponse(description="No such user."),
        },
        summary="Grant a time-bounded access override",
    )
    def post(self, request, pk):
        payload = AccessOverrideGrantSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        user = get_object_or_404(User.objects.all(), pk=pk)

        try:
            override = grant_access_override(
                actor=request.user,
                user=user,
                request=request,
                **payload.validated_data,
            )
        except InvalidOverride as exc:
            # 400 rather than 409: the request is malformed, not in conflict
            # with a state. The serializer catches most of these; this is the
            # backstop for a rule the serializer cannot express.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AccessOverrideSerializer(override).data, status=status.HTTP_201_CREATED)
