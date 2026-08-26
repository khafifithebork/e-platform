"""Content-Security-Policy on the Django tier. Abuse cases 1, 2 and 6.

**Report-only, and the tests say so out loud.** Under report-only every page
renders no matter how wrong the policy is, so "the admin still works" is not
evidence of anything — it would pass against a policy of `default-src 'none'`.
`TestTheAdminWouldSurviveEnforcement` is the test that means something: it
looks at what the admin page actually contains and compares it to what the
policy permits, which is the check a browser would do and the report endpoint
we do not have yet would tell us about.

The other half worth pinning is that the *enforcing* header is absent. A CSP
shipped enforcing without a report period is how a login form silently stops
working, and the difference between the two headers is one word.
"""

from __future__ import annotations

import importlib
import re

import pytest
from django.urls import clear_url_caches

PASSWORD = "a-long-enough-passphrase"
ADMIN_PATH = "staff-console-test"

pytestmark = pytest.mark.django_db

ENFORCING = "Content-Security-Policy"
REPORT_ONLY = "Content-Security-Policy-Report-Only"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def routed(settings):
    from config import urls as url_conf

    settings.ADMIN_PATH = ADMIN_PATH
    importlib.reload(url_conf)
    clear_url_caches()
    yield ADMIN_PATH

    settings.ADMIN_PATH = ""
    importlib.reload(url_conf)
    clear_url_caches()


def _staff(email: str = "staff@example.test"):
    from apps.accounts.models import Role
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    return user


def _directives(response) -> dict[str, str]:
    header = response.headers[REPORT_ONLY]
    parts = [part.strip() for part in header.split(";") if part.strip()]
    return {part.split(" ", 1)[0]: part for part in parts}


class TestItIsReportOnly:
    def test_the_report_only_header_is_present(self, client) -> None:
        response = client.get("/healthz")

        assert REPORT_ONLY in response.headers

    def test_and_the_enforcing_header_is_not(self, client) -> None:
        """The whole of ADR-022 §4 in one assertion. There is no deployment
        collecting reports until M13, so enforcing now is enforcing a policy
        nobody has observed — and the two headers differ by one word."""
        response = client.get("/healthz")

        assert ENFORCING not in response.headers

    def test_no_enforcing_policy_is_configured_at_all(self, settings) -> None:
        """Belt and braces: the header is absent because the setting is, not
        because a middleware happened not to run on this path."""
        assert not getattr(settings, "CONTENT_SECURITY_POLICY", None)


class TestWhatThePolicySays:
    def test_it_defaults_to_self(self, client) -> None:
        assert _directives(client.get("/healthz"))["default-src"] == "default-src 'self'"

    def test_scripts_are_not_allowed_inline(self, client) -> None:
        """The directive that matters for injection. If `unsafe-inline` ever
        appears here, the policy has stopped being a control."""
        script_src = _directives(client.get("/healthz"))["script-src"]

        assert "unsafe-inline" not in script_src
        assert "unsafe-eval" not in script_src

    def test_objects_and_framing_are_denied(self, client) -> None:
        directives = _directives(client.get("/healthz"))

        assert directives["object-src"] == "object-src 'none'"
        assert directives["frame-ancestors"] == "frame-ancestors 'none'"

    def test_the_base_uri_is_pinned(self, client) -> None:
        """Without it an injected `<base>` re-points every relative URL on the
        page, including the admin's own form actions."""
        assert _directives(client.get("/healthz"))["base-uri"] == "base-uri 'self'"

    def test_there_is_no_report_uri_until_one_is_configured(self, client) -> None:
        """A report-only policy with nowhere to report costs a few bytes and
        teaches nobody anything — but inventing an endpoint would be worse.
        M13 sets the variable."""
        assert "report-uri" not in _directives(client.get("/healthz"))


class TestTheAdminWouldSurviveEnforcement:
    """Abuse case 2, checked rather than assumed.

    Under report-only the admin renders whatever the policy says, so asserting
    "it returns 200" proves nothing — it would pass against
    `default-src 'none'`. So this inspects the markup the admin actually sends
    and asks whether the policy would permit it, which is what a browser does
    and what the report endpoint M13 adds would tell us.
    """

    def _admin_html(self, client, routed) -> str:
        from tests.otp_helpers import verify_admin_session

        staff = _staff()
        client.force_login(staff)
        verify_admin_session(client, staff.email)

        response = client.get(f"/{routed}/", follow=True)
        assert response.status_code == 200
        return response.content.decode()

    def test_the_admin_renders_at_all(self, client, routed) -> None:
        """The positive twin. Every assertion below would pass over an error
        page."""
        assert "dashboard" in self._admin_html(client, routed).lower()

    def test_it_ships_no_inline_script_the_policy_would_block(self, client, routed) -> None:
        """`script-src 'self'` blocks an inline `<script>` with executable
        content. Django's admin uses `<script type="application/json">` for
        data, which browsers do not execute and CSP does not block, so those
        are excluded deliberately rather than by accident.
        """
        html = self._admin_html(client, routed)

        executable = [
            block
            for block in re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
            if block[1].strip() and "application/json" not in block[0]
        ]

        assert executable == [], executable

    def test_it_ships_no_inline_event_handlers(self, client, routed) -> None:
        """`onclick=` and friends are blocked by `script-src` without
        `unsafe-inline`, and are the most common reason an admin page dies
        under CSP."""
        html = self._admin_html(client, routed)

        handlers = re.findall(r"\son(?:click|load|error|submit|change)\s*=", html, re.I)

        assert handlers == [], handlers

    def test_inline_styles_are_the_known_exception(self, client, routed) -> None:
        """Recorded rather than fixed. If the admin does carry inline styles,
        `style-src 'self'` would report them — and this test is where that fact
        lives so enforcement in M13 is a decision rather than a surprise.

        Asserted as a *count*, so the number moving is visible in a diff.
        """
        html = self._admin_html(client, routed)

        inline_styles = re.findall(r'\sstyle\s*=\s*"', html)

        assert len(inline_styles) <= 2, (
            f"{len(inline_styles)} inline style attributes on the admin index; "
            "style-src 'self' would report each one"
        )


class TestNoOtherSecurityHeaderRegressed:
    """Abuse case 7 in the spec, brought forward because adding a middleware is
    exactly when a header ordering mistake would show up."""

    def test_the_usual_headers_are_still_there(self, client) -> None:
        response = client.get("/healthz")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_the_csp_middleware_is_next_to_the_security_middleware(self, settings) -> None:
        """Not a correctness property — a findability one. Header-setting
        middleware belongs together so the next person looking for "where are
        the headers" finds them in one place."""
        middleware = list(settings.MIDDLEWARE)
        security = middleware.index("django.middleware.security.SecurityMiddleware")

        assert middleware[security + 1] == "csp.middleware.CSPMiddleware"
