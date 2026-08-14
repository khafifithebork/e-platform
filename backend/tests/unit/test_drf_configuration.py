"""Contracts for the DRF configuration.

These are settings assertions, which is usually a weak kind of test. They earn
their place because each one encodes an invariant that is invisible at the call
site: nothing in a view will ever remind you that authentication is
session-only or that the cache is shared with the task queue.
"""

from __future__ import annotations


class TestAuthentication:
    def test_only_session_authentication_is_enabled(self) -> None:
        """Invariant 9. Sessions, not JWTs — the argument is in
        architecture.md 4.2 and turns on instant revocation."""
        from django.conf import settings

        classes = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]

        assert classes == ["rest_framework.authentication.SessionAuthentication"]

    def test_no_token_or_jwt_authentication_anywhere(self) -> None:
        """A second, blunter guard. Adding a token class is exactly the sort of
        change that arrives with a plausible justification attached."""
        from django.conf import settings

        joined = " ".join(settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]).lower()

        assert "jwt" not in joined
        assert "token" not in joined


class TestPermissions:
    def test_endpoints_are_closed_by_default(self) -> None:
        """Deny by default, so exposing an endpoint is a deliberate act rather
        than the consequence of forgetting a permission class."""
        from django.conf import settings

        classes = settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]

        assert classes == ["rest_framework.permissions.IsAuthenticated"]


class TestRenderers:
    def test_only_json_is_rendered(self) -> None:
        """The browsable API is a development convenience. In production it is
        an HTML surface that enumerates endpoints and echoes data back."""
        from django.conf import settings

        renderers = settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]

        assert renderers == ["rest_framework.renderers.JSONRenderer"]


class TestThrottling:
    def test_anonymous_and_authenticated_rates_are_configured(self) -> None:
        """architecture.md 6.4."""
        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

        assert rates["anon"] == "60/min"
        assert rates["user"] == "300/min"


class TestCache:
    def test_the_test_suite_uses_local_memory(self) -> None:
        """Deliberate, and the reason is worth stating where someone will read it.

        DRF throttling counts against the default cache, so any test touching a
        real view opens a cache connection. Pointing that at Redis makes the
        suite pass only on a machine that happens to be running one — which CI
        is not. The production configuration is asserted separately, against
        production settings, in test_settings.py.
        """
        from django.conf import settings

        assert settings.CACHES["default"]["BACKEND"] == (
            "django.core.cache.backends.locmem.LocMemCache"
        )
