"""The CSRF origin check, behind a proxy.

This is here because the setting was missing and nothing noticed. Django
compares the browser's `Origin` against its own idea of its origin, and behind
the Next.js rewrite those are never the same host — Next forwards the rewrite
destination as `Host`, which is the fact `local.py` already records about
`ALLOWED_HOSTS`. The result was that every unsafe request through the proxy was
refused with "Origin checking failed", including login, and the only way to
find out was to watch a page fail to save anything.

So both halves are asserted: an untrusted origin is refused, and a trusted one
is not. Either alone would pass with the check broken in one direction.
"""

from __future__ import annotations

import pytest
from django.test import Client

LOGOUT = "/api/v1/auth/logout/"
CSRF = "/api/v1/auth/csrf/"

PASSWORD = "a-sufficiently-long-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def account(db):
    from apps.accounts.services import create_account

    return create_account(email="learner@example.test", password=PASSWORD)


def _post_from(origin: str, user):
    """An authenticated write carrying an Origin header, CSRF enforced.

    **Signed in on purpose.** DRF only checks CSRF inside
    `SessionAuthentication`, which runs when a session cookie identifies
    somebody — so an anonymous POST never reaches the origin check at all. The
    first version of this test used login while logged out and returned 200 for
    an attacker's origin, which looked like a hole and was really a test that
    never provoked the control. Every write this protects — a heartbeat, a
    review decision — is authenticated.

    The default test client skips CSRF entirely, which is how a broken origin
    list sits in a codebase with a full suite passing over it.
    """
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    token = client.get(CSRF).cookies["csrftoken"].value

    return client.post(
        LOGOUT,
        {},
        content_type="application/json",
        headers={"origin": origin, "x-csrftoken": token},
    )


class TestOnlyTrustedOriginsMayWrite:
    def test_an_untrusted_origin_is_refused(self, settings, account) -> None:
        settings.CSRF_TRUSTED_ORIGINS = ["https://lingua.example"]

        response = _post_from("https://attacker.example", account)

        assert response.status_code == 403

    def test_a_trusted_origin_is_allowed(self, settings, account) -> None:
        """The half that was actually broken. With no trusted origin
        configured, this is the request that fails in every deployment sitting
        behind a proxy — which is all of them."""
        settings.CSRF_TRUSTED_ORIGINS = ["https://lingua.example"]

        response = _post_from("https://lingua.example", account)

        assert response.status_code == 200

    def test_configuring_nothing_trusts_nothing(self, settings, account) -> None:
        """The empty default is deliberate: a deployment that forgets to set
        this fails loudly on its first write rather than quietly trusting an
        origin somebody could guess."""
        settings.CSRF_TRUSTED_ORIGINS = []

        assert _post_from("https://lingua.example", account).status_code == 403


class TestTheSettingIsReadFromTheEnvironment:
    def test_it_is_not_hardcoded(self) -> None:
        """A literal list in settings would be right for one environment and
        wrong for every other, and nobody would find out until a deploy."""
        from pathlib import Path

        base = Path(__file__).resolve().parents[2] / "config" / "settings" / "base.py"
        source = base.read_text(encoding="utf-8")

        assert 'CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS"' in source
