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
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.entitlements.permissions import IsAdministrator
from apps.entitlements.resolver import resolve_account_access
from apps.entitlements.selectors import diagnostics_for
from apps.entitlements.serializers import UserDiagnosticsSerializer


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
