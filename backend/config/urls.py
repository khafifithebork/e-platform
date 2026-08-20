"""Root URL configuration.

Product endpoints arrive in later milestones. Django Admin is installed but
deliberately not routed: it is the highest-value target in the system and stays
unreachable until it is hardened in M10 (obscure path, staff-only, 2FA, audit
logging).
"""

from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import healthz

urlpatterns: list[URLPattern | URLResolver] = [
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/instructor/", include("apps.catalog.urls")),
    # The only unauthenticated product surface. Separate prefix so the
    # public/private boundary is actionable at the edge.
    path("api/v1/catalogue/", include("apps.catalog.public_urls")),
    # Paid content. Every route here passes the entitlement resolver.
    path("api/v1/", include("apps.catalog.learning_urls")),
    # Uploads. Bytes go browser to store; these two routes are JSON only.
    path("api/v1/", include("apps.media_assets.urls")),
    # Administrators only, every route. Not the Django admin site, which M10
    # routes separately after hardening.
    path("api/v1/admin-api/", include("apps.entitlements.admin_urls")),
    # Infrastructure, not product: outside /api/v1/ on purpose, so it is not
    # versioned, not in the OpenAPI schema, and not proxied as an API route.
    path("healthz", healthz, name="healthz"),
    # The contract. Frontend types are generated from this (invariant 16), and
    # a test asserts the committed docs/openapi.yaml still matches the code.
    #
    # Readable without authentication, which DRF's deny-by-default requires an
    # explicit exemption for. Publishing the surface is deliberate: hiding it
    # would be obscurity rather than security, since every endpoint is
    # protected by its own permission check and that is what actually holds.
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
