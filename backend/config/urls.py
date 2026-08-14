"""Root URL configuration.

Product endpoints arrive in later milestones. Django Admin is installed but
deliberately not routed: it is the highest-value target in the system and stays
unreachable until it is hardened in M10 (obscure path, staff-only, 2FA, audit
logging).
"""

from django.urls import URLPattern, URLResolver, path

from apps.core.views import healthz

urlpatterns: list[URLPattern | URLResolver] = [
    # Infrastructure, not product: outside /api/v1/ on purpose, so it is not
    # versioned, not in the OpenAPI schema, and not proxied as an API route.
    path("healthz", healthz, name="healthz"),
]
