"""Password hashing, session cookies, and brute-force lockout.

These are settings assertions, and they earn their place the same way the DRF
ones do: nothing at a call site will ever remind you that the cookie is
HttpOnly or that Argon2 is first in the list. They are also the controls whose
absence is invisible until it is exploited.
"""

from __future__ import annotations

import secrets
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

_PROBE = (
    "import importlib, sys; "
    "module = importlib.import_module(sys.argv[1]); "
    "print(getattr(module, sys.argv[2]))"
)


def _production_setting(name: str) -> str:
    """Read a setting from production settings in a clean interpreter."""
    environment = {
        "PATH": __import__("os").environ["PATH"],
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DJANGO_ALLOWED_HOSTS": "example.test",
        "DATABASE_URL": "postgres://localhost:5432/app",
        "REDIS_URL": "redis://localhost:6379/0",
        "REDIS_CACHE_URL": "redis://localhost:6379/1",
        # Required by base.py with no default from M5. Nothing connects; this
        # probe only reads a setting back.
        "MEDIA_STORAGE_ENDPOINT": "https://storage.example.test",
        "MEDIA_STORAGE_BUCKET": "media",
        "MEDIA_STORAGE_ACCESS_KEY": secrets.token_urlsafe(16),
        "MEDIA_STORAGE_SECRET_KEY": secrets.token_urlsafe(32),
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _PROBE, "config.settings.production", name],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestPasswordHashing:
    def test_argon2_is_the_default(self) -> None:
        """architecture.md §4.2. Stronger than Django's PBKDF2 default, and
        the winner of the Password Hashing Competition — memory-hard, so a
        GPU farm buys an attacker much less than it does against PBKDF2."""
        from django.conf import settings

        assert settings.PASSWORD_HASHERS[0] == ("django.contrib.auth.hashers.Argon2PasswordHasher")

    def test_pbkdf2_is_retained_below_it(self) -> None:
        """Not decoration. Django upgrades a hash on next successful login, so
        removing the old hasher would lock out every account created before
        the switch — it could no longer verify their stored password."""
        from django.conf import settings

        assert any("PBKDF2" in hasher for hasher in settings.PASSWORD_HASHERS[1:])

    def test_a_password_is_actually_hashed_with_argon2(self) -> None:
        """Configuration proves intent; this proves effect."""
        from django.contrib.auth.hashers import make_password

        assert make_password("pw-for-this-test").startswith("argon2$")


class TestSessionCookie:
    def test_not_readable_from_javascript(self) -> None:
        """Invariant 9 and the whole argument in §4.1: HttpOnly is what makes
        XSS unable to steal the session."""
        from django.conf import settings

        assert settings.SESSION_COOKIE_HTTPONLY is True

    def test_same_site_lax(self) -> None:
        from django.conf import settings

        assert settings.SESSION_COOKIE_SAMESITE == "Lax"
        assert settings.CSRF_COOKIE_SAMESITE == "Lax"

    def test_https_only_in_production(self) -> None:
        """Asserted against production settings, because local development
        runs over http and cannot set this."""
        assert _production_setting("SESSION_COOKIE_SECURE") == "True"
        assert _production_setting("CSRF_COOKIE_SECURE") == "True"

    def test_stored_in_the_database(self) -> None:
        """Sessions outlive Redis. §4.2: logging everyone out because a cache
        evicted is a bad afternoon."""
        from django.conf import settings

        assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"


class TestBruteForceLockout:
    def test_axes_is_installed(self) -> None:
        from django.conf import settings

        assert "axes" in settings.INSTALLED_APPS

    def test_the_axes_backend_runs_before_the_model_backend(self) -> None:
        """Order is the control. AxesStandaloneBackend must see the attempt
        first; behind ModelBackend it would be consulted only after Django had
        already authenticated the request, which is too late to refuse."""
        from django.conf import settings

        backends = settings.AUTHENTICATION_BACKENDS

        assert backends[0] == "axes.backends.AxesStandaloneBackend"
        assert "django.contrib.auth.backends.ModelBackend" in backends[1:]

    def test_the_middleware_is_installed(self) -> None:
        from django.conf import settings

        assert "axes.middleware.AxesMiddleware" in settings.MIDDLEWARE

    def test_lockout_is_bounded_and_temporary(self) -> None:
        """A permanent lockout is a denial-of-service an attacker can trigger
        against any account whose email they know."""
        from django.conf import settings

        assert settings.AXES_FAILURE_LIMIT == 5
        assert settings.AXES_COOLOFF_TIME == 1

    def test_lockout_keys_on_username_and_ip_together(self) -> None:
        """IP alone punishes everyone behind one NAT; username alone lets an
        attacker lock a known account out from anywhere. Combining them is
        what makes the control usable."""
        from django.conf import settings

        assert settings.AXES_LOCKOUT_PARAMETERS == [["username", "ip_address"]]
