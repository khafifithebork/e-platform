"""Root URL configuration.

Deliberately empty. M0 ships no endpoints — /healthz, the DRF schema and the
Problem Details error shape all arrive in M1. Django Admin is installed but not
routed: it is the highest-value target in the system and stays unrouted until
it is hardened in M10 (obscure path, staff-only, 2FA, audit logging).
"""

from django.urls import URLPattern, URLResolver

urlpatterns: list[URLPattern | URLResolver] = []
