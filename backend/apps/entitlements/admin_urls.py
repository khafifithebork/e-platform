"""Administrator-only entitlement routes.

Its own prefix so the boundary is visible in the path: everything under
`/admin-api/` requires `role == ADMIN`, and nothing else does. Not `/admin/`,
which is reserved for the Django admin site when M10 routes it.
"""

from django.urls import path

from apps.entitlements.admin_views import UserDiagnosticsView

app_name = "entitlements-admin"

urlpatterns = [
    path(
        "users/<uuid:pk>/diagnostics/",
        UserDiagnosticsView.as_view(),
        name="user-diagnostics",
    ),
]
