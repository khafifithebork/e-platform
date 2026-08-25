"""Password hashing, session cookies, and brute-force lockout.

These are settings assertions, and they earn their place the same way the DRF
ones do: nothing at a call site will ever remind you that the cookie is
HttpOnly or that Argon2 is first in the list. They are also the controls whose
absence is invisible until it is exploited.
"""

from __future__ import annotations

import ast
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

# Reading a setting proves intent; this proves effect. It has to run out of
# process because the suite itself deliberately configures a fast hasher
# (config/settings/test.py), so an in-process `make_password` would report the
# suite's choice rather than production's.
_HASH_PROBE = (
    "import os, django; "
    "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'; "
    "django.setup(); "
    "from django.contrib.auth.hashers import make_password; "
    "print(make_password(os.environ['PROBE_PASSWORD']))"
)


def _production_environment() -> dict[str, str]:
    """A complete production environment for a probe subprocess.

    Secrets are generated per call rather than written literally, because
    CLAUDE.md §6 forbids environment variable *values* in code or tests even
    when they are throwaway.
    """
    return {
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


def _run_probe(script: str, *args: str, **extra_environment: str) -> str:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, *args],
        cwd=BACKEND_ROOT,
        env=_production_environment() | extra_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _production_setting(name: str) -> str:
    """Read a setting from production settings in a clean interpreter."""
    return _run_probe(_PROBE, "config.settings.production", name)


def _production_hashers() -> list[str]:
    """The production hasher list, as a list.

    The probe prints `str(list)`, which is a Python literal, so this parses it
    back rather than matching on substrings — a `split` on the printed form
    fails with an IndexError instead of an assertion when the list is short,
    which is a worse signal than the one it is trying to give.
    """
    return ast.literal_eval(_production_setting("PASSWORD_HASHERS"))


def _hash_under_production_settings(password: str) -> str:
    """Hash a password with whatever production is actually configured to use."""
    return _run_probe(_HASH_PROBE, PROBE_PASSWORD=password)


class TestPasswordHashing:
    """Asserted against *production* settings, not the running suite.

    The suite configures MD5 for speed (config/settings/test.py explains why),
    so reading `django.conf.settings` here would assert the suite's own
    shortcut and pass forever no matter what production did — an inert control
    of exactly the shape ADR-006 exists to catch. Every case below therefore
    loads production in a clean interpreter.
    """

    def test_argon2_is_the_default(self) -> None:
        """architecture.md §4.2. Stronger than Django's PBKDF2 default, and
        the winner of the Password Hashing Competition — memory-hard, so a
        GPU farm buys an attacker much less than it does against PBKDF2."""
        assert _production_hashers()[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"

    def test_pbkdf2_is_retained_below_it(self) -> None:
        """Not decoration. Django upgrades a hash on next successful login, so
        removing the old hasher would lock out every account created before
        the switch — it could no longer verify their stored password."""
        assert any("PBKDF2" in hasher for hasher in _production_hashers()[1:])

    def test_a_password_is_actually_hashed_with_argon2(self) -> None:
        """Configuration proves intent; this proves effect."""
        assert _hash_under_production_settings("pw-for-this-test").startswith("argon2$")

    def test_and_the_suite_is_the_only_thing_that_relaxes_it(self) -> None:
        """The twin, and the reason the relaxation is safe to leave in place.

        If test settings ever stopped overriding the hashers this would fail,
        which is the signal that the three cases above could have gone back to
        reading live settings — and, more usefully, that an hour-long suite had
        quietly returned."""
        from django.conf import settings

        assert settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]


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
