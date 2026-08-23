"""Root URL configuration.

**The Django admin is routed only when `DJANGO_ADMIN_PATH` is set.** M10
hardened it — an unguessable path, staff-only, 2FA — and until M10 it was not
routed at all. The conditional is deliberate: an environment that has not
chosen a path gets no admin site, rather than one at a location that would have
had to be written down in this repository to be a default.
"""

from django.conf import settings
from django.contrib import admin
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
    path("api/v1/", include("apps.transcripts.urls")),
    path("api/v1/", include("apps.learning.urls")),
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

# Appended rather than declared inline, so the list above reads the same in
# every environment and the one path that varies is visibly conditional.
#
# Staff-only comes free: `AdminSite.has_permission` requires `is_active` and
# `is_staff`, and this codebase grants `is_staff` deliberately rather than with
# a role — an ADMIN is not automatically staff (accounts.models). So routing
# this exposes it to superusers and to nobody else.
if settings.ADMIN_PATH:
    urlpatterns.append(path(f"{settings.ADMIN_PATH}/", admin.site.urls))
