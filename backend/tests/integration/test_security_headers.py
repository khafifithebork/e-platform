"""Every security header, on every kind of response. Abuse case 7.

Spot-checking headers is how one goes missing. The failure is not "somebody
deleted `SECURE_CONTENT_TYPE_NOSNIFF`" — it is a middleware reordered, or a
view that builds its own `HttpResponse`, or an error path that returns before
the middleware that would have set them. So this sweeps: several kinds of
response, including a 404 and a refusal, against one declared set.

**The transport headers are asserted against production, not against this
suite.** `Strict-Transport-Security` is only emitted when the request is
secure *and* `SECURE_HSTS_SECONDS` is set, and neither is true under pytest.
Asserting it here would mean asserting `None == None` and calling it a
control — the inert-control shape ADR-006 exists for. They are read out of
production settings in a clean interpreter instead.
"""

from __future__ import annotations

import secrets
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

PASSWORD = "a-long-enough-passphrase"
BACKEND_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.django_db

# Measured from what the stack actually emits, not listed from memory. Each is
# here because something sets it deliberately:
#
# - nosniff: SECURE_CONTENT_TYPE_NOSNIFF, stops a browser second-guessing a
#   content type and executing an uploaded file as script.
# - Referrer-Policy: same-origin, so a lesson URL is not leaked to whatever a
#   learner clicks through to.
# - Cross-Origin-Opener-Policy: same-origin, which severs `window.opener` and
#   is what makes a tab-napping attack on a signed-in session fail.
# - CSP report-only: M12 T5.
EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}

ALWAYS_PRESENT = ("Content-Security-Policy-Report-Only",)


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _responses(client) -> dict[str, object]:
    """One of each shape of response the stack produces.

    A 404 and a 403 are here because an error path is the one most likely to
    return before the middleware that sets these — and an attacker sees error
    responses more often than anyone else does.
    """
    return {
        "infrastructure (healthz)": client.get("/healthz"),
        "public catalogue": client.get("/api/v1/catalogue/courses/"),
        "public search": client.get("/api/v1/catalogue/search/", {"q": "spanish"}),
        "openapi schema": client.get("/api/v1/schema/"),
        "404": client.get("/no-such-path-anywhere/"),
        "403 refusal": client.get(f"/api/v1/admin-api/users/{uuid.uuid4()}/diagnostics/"),
    }


class TestEveryResponseCarriesThem:
    @pytest.mark.parametrize(("header", "value"), sorted(EXPECTED_HEADERS.items()))
    def test_the_header_is_present_everywhere(self, client, header: str, value: str) -> None:
        for label, response in _responses(client).items():
            assert response.headers.get(header) == value, (
                f"{header} missing or wrong on the {label} response "
                f"(got {response.headers.get(header)!r})"
            )

    def test_the_csp_is_present_everywhere(self, client) -> None:
        for label, response in _responses(client).items():
            for header in ALWAYS_PRESENT:
                assert header in response.headers, f"{header} missing on the {label} response"

    def test_the_sweep_covers_more_than_one_response(self, client) -> None:
        """A sweep over an empty mapping passes forever, which is the failure
        this codebase keeps finding in its own guards."""
        assert len(_responses(client)) >= 5

    def test_and_the_responses_are_the_ones_intended(self, client) -> None:
        """The second twin. If every entry above started 500ing, the headers
        would still be attached and the sweep would still pass — so the status
        codes are pinned too."""
        responses = _responses(client)

        assert responses["infrastructure (healthz)"].status_code == 200
        assert responses["public catalogue"].status_code == 200
        assert responses["public search"].status_code == 200
        assert responses["404"].status_code == 404
        assert responses["403 refusal"].status_code in (401, 403)


class TestNoResponseIsFramable:
    """`X-Frame-Options` comes from a different middleware than the rest, so it
    is swept separately — and CSP's `frame-ancestors` is the modern half that
    browsers prefer when the two disagree."""

    def test_x_frame_options_denies(self, client) -> None:
        for label, response in _responses(client).items():
            assert response.headers.get("X-Frame-Options") == "DENY", label

    def test_and_the_csp_says_the_same_thing(self, client) -> None:
        policy = client.get("/healthz").headers["Content-Security-Policy-Report-Only"]

        assert "frame-ancestors 'none'" in policy


def _production_setting(name: str) -> str:
    """Read a setting from production settings in a clean interpreter.

    The same technique `test_auth_hardening.py` uses, and for the same reason:
    these values are not active in the test settings, so reading
    `django.conf.settings` would assert the suite's own configuration.
    """
    probe = (
        "import importlib, sys; "
        "module = importlib.import_module('config.settings.production'); "
        "print(getattr(module, sys.argv[1]))"
    )
    environment = {
        "PATH": __import__("os").environ["PATH"],
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DJANGO_ALLOWED_HOSTS": "example.test",
        "DATABASE_URL": "postgres://localhost:5432/app",
        "REDIS_URL": "redis://localhost:6379/0",
        "REDIS_CACHE_URL": "redis://localhost:6379/1",
        "MEDIA_STORAGE_ENDPOINT": "https://storage.example.test",
        "MEDIA_STORAGE_BUCKET": "media",
        "MEDIA_STORAGE_ACCESS_KEY": secrets.token_urlsafe(16),
        "MEDIA_STORAGE_SECRET_KEY": secrets.token_urlsafe(32),
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe, name],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestTransportSecurityInProduction:
    """These were configured in M0 and asserted nowhere.

    `Strict-Transport-Security` is emitted only on a secure request with
    `SECURE_HSTS_SECONDS` set, and neither holds under pytest — so a test here
    would compare `None` to `None` and read like a control.
    """

    def test_hsts_is_a_year(self) -> None:
        """Shorter than a few months and a browser has forgotten by the time it
        matters; the preload list requires at least a year."""
        assert int(_production_setting("SECURE_HSTS_SECONDS")) >= 31_536_000

    def test_hsts_covers_subdomains_and_is_preloadable(self) -> None:
        assert _production_setting("SECURE_HSTS_INCLUDE_SUBDOMAINS") == "True"
        assert _production_setting("SECURE_HSTS_PRELOAD") == "True"

    def test_plain_http_is_redirected(self) -> None:
        assert _production_setting("SECURE_SSL_REDIRECT") == "True"

    def test_the_proxy_header_is_declared(self) -> None:
        """Without it Django believes every request behind the edge is
        insecure, and `SECURE_SSL_REDIRECT` becomes an infinite redirect rather
        than a control."""
        assert "HTTP_X_FORWARDED_PROTO" in _production_setting("SECURE_PROXY_SSL_HEADER")

    def test_nosniff_is_on_in_production_too(self) -> None:
        """Asserted separately from the response sweep: the sweep proves the
        header ships under *test* settings, and this proves the setting that
        produces it survives in production."""
        assert _production_setting("SECURE_CONTENT_TYPE_NOSNIFF") == "True"
