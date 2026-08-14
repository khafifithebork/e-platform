"""Contracts for the DRF configuration.

These are settings assertions, which is usually a weak kind of test. They earn
their place because each one encodes an invariant that is invisible at the call
site: nothing in a view will ever remind you that authentication is
session-only or that the cache is shared with the task queue.
"""

from __future__ import annotations

from urllib.parse import urlparse


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
    def test_cache_is_redis_not_local_memory(self) -> None:
        """Invariant 5. DRF throttling counts against the default cache, and
        Django's LocMemCache default is per-process — throttles would silently
        become per-worker the moment there is more than one."""
        from django.conf import settings

        assert settings.CACHES["default"]["BACKEND"] == (
            "django.core.cache.backends.redis.RedisCache"
        )

    def test_cache_and_celery_broker_use_different_redis_databases(self) -> None:
        """Sharing one database means `cache.clear()` deletes queued tasks.

        That is a genuinely nasty failure: the queue empties silently, nothing
        errors, and the work simply never happens.
        """
        from django.conf import settings

        cache_db = urlparse(settings.CACHES["default"]["LOCATION"]).path
        broker_db = urlparse(settings.CELERY_BROKER_URL).path

        assert cache_db != broker_db, (
            f"cache and broker share Redis database {cache_db!r}; "
            "a cache flush would drop queued tasks"
        )
