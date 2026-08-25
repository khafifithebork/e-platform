"""Administrator-only entitlement routes.

Its own prefix so the boundary is visible in the path: everything under
`/admin-api/` requires `role == ADMIN`, and nothing else does. Not `/admin/`,
which is reserved for the Django admin site when M10 routes it.
"""

from django.urls import path

from apps.entitlements.admin_views import (
    SubscriptionRefundView,
    UserAccessOverrideView,
    UserDiagnosticsView,
)

app_name = "entitlements-admin"

urlpatterns = [
    path(
        "users/<uuid:pk>/diagnostics/",
        UserDiagnosticsView.as_view(),
        name="user-diagnostics",
    ),
    path(
        "users/<uuid:pk>/access-override/",
        UserAccessOverrideView.as_view(),
        name="user-access-override",
    ),
    path(
        "subscriptions/<uuid:pk>/refund/",
        SubscriptionRefundView.as_view(),
        name="subscription-refund",
    ),
]
