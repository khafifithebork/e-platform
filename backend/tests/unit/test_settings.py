"""Contracts that the settings modules must hold.

Each case loads a settings module in a *fresh interpreter* rather than
importing it in-process. Django settings are import-time side effects and
Python caches modules, so in-process reload tests are unreliable and
order-dependent. A subprocess gives every case a genuinely clean environment,
which is the whole point when the behaviour under test is "what happens when
an environment variable is absent".
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Import a settings module and print one attribute from it.
_PROBE = (
    "import importlib, sys; "
    "module = importlib.import_module(sys.argv[1]); "
    "print(getattr(module, sys.argv[2]))"
)


def _valid_environment() -> dict[str, str]:
    """A complete production environment.

    The secret is generated per call rather than written literally, because
    CLAUDE.md section 6 forbids environment variable *values* in code or tests
    even when they are throwaway.
    """
    return {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DJANGO_ALLOWED_HOSTS": "example.test",
        "DATABASE_URL": "postgres://localhost:5432/app",
        "REDIS_URL": "redis://localhost:6379/0",
        # Database 1: the cache must not share a Redis database with the
        # Celery broker, or a cache flush drops queued tasks.
        "REDIS_CACHE_URL": "redis://localhost:6379/1",
    }


def _read_setting(module: str, name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Import `module` in a clean interpreter and print the value of `name`."""
    # Only pass through what the interpreter needs to start. Anything else
    # would let the developer's own shell leak in and mask a missing variable.
    clean = {"PATH": os.environ["PATH"], "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    clean.update(env)
    # S603: the command is this interpreter plus a fixed probe string. Both
    # arguments are module and attribute names chosen by the test, never user
    # input, and no shell is involved.
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", _PROBE, module, name],
        cwd=BACKEND_ROOT,
        env=clean,
        capture_output=True,
        text=True,
        check=False,
    )


class TestProductionSettingsFailFast:
    """A missing variable must stop the process, never fall back to a default.

    Silent defaults are how a system ends up running in production with a
    development secret key.
    """

    def test_refuses_to_load_without_a_secret_key(self) -> None:
        environment = _valid_environment()
        del environment["DJANGO_SECRET_KEY"]

        result = _read_setting("config.settings.production", "DEBUG", environment)

        assert result.returncode != 0
        assert "ImproperlyConfigured" in result.stderr

    def test_refuses_to_load_without_a_database_url(self) -> None:
        environment = _valid_environment()
        del environment["DATABASE_URL"]

        result = _read_setting("config.settings.production", "DEBUG", environment)

        assert result.returncode != 0
        assert "ImproperlyConfigured" in result.stderr

    def test_loads_when_every_required_variable_is_present(self) -> None:
        result = _read_setting("config.settings.production", "DEBUG", _valid_environment())

        assert result.returncode == 0, result.stderr


class TestProductionSettingsHardening:
    def test_debug_is_disabled(self) -> None:
        """DEBUG on in production leaks settings and stack traces to the world."""
        result = _read_setting("config.settings.production", "DEBUG", _valid_environment())

        assert result.stdout.strip() == "False"

    def test_debug_cannot_be_switched_on_by_the_environment(self) -> None:
        """The base module reads DJANGO_DEBUG; production must override it."""
        environment = _valid_environment()
        environment["DJANGO_DEBUG"] = "true"

        result = _read_setting("config.settings.production", "DEBUG", environment)

        assert result.stdout.strip() == "False"

    def test_sessions_are_stored_in_the_database(self) -> None:
        """Invariant 9. Redis is disposable; a cache eviction must not log
        every user out."""
        result = _read_setting("config.settings.production", "SESSION_ENGINE", _valid_environment())

        assert result.stdout.strip() == "django.contrib.sessions.backends.db"


class TestLocalSettings:
    def test_allowed_hosts_are_read_from_the_environment(self) -> None:
        """Regression: local settings used to hardcode ALLOWED_HOSTS.

        The compose stack reaches Django as `api`, because Next.js forwards the
        rewrite destination as the Host header. A hardcoded list in local
        settings silently overrode DJANGO_ALLOWED_HOSTS, so the variable set in
        docker-compose.yml had no effect and every proxied request failed with
        DisallowedHost. Nothing short of running the whole stack caught it.
        """
        environment = _valid_environment()
        environment["DJANGO_ALLOWED_HOSTS"] = "api,example.test"

        result = _read_setting("config.settings.local", "ALLOWED_HOSTS", environment)

        assert result.returncode == 0, result.stderr
        assert "api" in result.stdout


class TestAsgiOnly:
    def test_no_wsgi_module_exists(self) -> None:
        """Invariant 12. architecture.md section 9 lists a wsgi.py; ADR-001
        section 2.4 deliberately omits it so that reverting to WSGI requires a
        decision rather than an import."""
        assert not (BACKEND_ROOT / "config" / "wsgi.py").exists()

    def test_asgi_application_is_configured(self) -> None:
        result = _read_setting(
            "config.settings.production", "ASGI_APPLICATION", _valid_environment()
        )

        assert result.stdout.strip() == "config.asgi.application"
