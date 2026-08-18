"""Login, logout, and the lockout.

Abuse case 6 is the one this task exists to prove: five wrong passwords lock
the account, and changing the User-Agent does not get around it. That last part
is the whole point — a lockout keyed on anything the attacker controls is
theatre.

The revocation property that justified sessions over JWT (§4.2) is asserted
here too: deleting the session row signs the user out immediately.
"""

from __future__ import annotations

import pytest
from django.contrib.sessions.models import Session

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
CSRF = "/api/v1/auth/csrf/"

PASSWORD = "a-sufficiently-long-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    """Raise limits rather than remove them — several tests here deliberately
    hammer one endpoint, and DRF rejects a scope with no rate."""
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


@pytest.fixture(autouse=True)
def _reset_lockouts(db):
    """django-axes persists failures. Without this, one test's failed attempts
    lock the account for the next."""
    from axes.models import AccessAttempt

    AccessAttempt.objects.all().delete()
    yield
    AccessAttempt.objects.all().delete()


def _login(client, email: str, password: str, **extra):
    return client.post(
        LOGIN, {"email": email, "password": password}, content_type="application/json", **extra
    )


@pytest.mark.django_db
class TestLogin:
    def test_valid_credentials_establish_a_session(self, client, account) -> None:
        response = _login(client, account.email, PASSWORD)

        assert response.status_code == 200
        assert "_auth_user_id" in client.session

    def test_the_session_cookie_is_not_readable_by_javascript(self, client, account) -> None:
        """Invariant 9. HttpOnly is what makes XSS unable to steal the session,
        and is the reason sessions beat a token in localStorage."""
        _login(client, account.email, PASSWORD)

        assert client.cookies["sessionid"]["httponly"] is True

    def test_the_session_key_changes_on_login(self, client, account) -> None:
        """Session fixation: an attacker who can set a victim's session cookie
        before login must not still hold a valid one afterwards."""
        client.get(CSRF)
        before = client.session.session_key

        _login(client, account.email, PASSWORD)

        assert client.session.session_key != before

    def test_an_unverified_account_may_sign_in(self, client, account) -> None:
        """ADR-005 §2.3. Verification gates starting a trial (§7.1), not
        logging in — an email stuck in a spam folder should not lock someone
        out of the account they just made."""
        assert account.is_email_verified is False

        assert _login(client, account.email, PASSWORD).status_code == 200

    def test_the_password_is_never_echoed(self, client, account) -> None:
        response = _login(client, account.email, PASSWORD)

        assert PASSWORD not in response.content.decode()


@pytest.mark.django_db
class TestFailedLoginRevealsNothing:
    """A login endpoint is an enumeration oracle unless it is built not to be."""

    def test_a_wrong_password_is_refused(self, client, account) -> None:
        response = _login(client, account.email, "not-the-right-password")

        assert response.status_code == 400
        assert "_auth_user_id" not in client.session

    def test_an_unknown_address_looks_identical_to_a_wrong_password(self, client, account) -> None:
        wrong_password = _login(client, account.email, "not-the-right-password")
        unknown_account = _login(client, "nobody@example.test", "not-the-right-password")

        assert wrong_password.status_code == unknown_account.status_code
        assert wrong_password.json() == unknown_account.json()


@pytest.mark.django_db
class TestLockout:
    """Abuse case 6."""

    def _fail(self, client, account, times: int, **extra):
        for _ in range(times):
            _login(client, account.email, "not-the-right-password", **extra)

    def test_repeated_failures_lock_the_account(self, client, account, settings) -> None:
        self._fail(client, account, settings.AXES_FAILURE_LIMIT)

        # Correct credentials now, and still refused.
        assert _login(client, account.email, PASSWORD).status_code != 200
        assert "_auth_user_id" not in client.session

    def test_changing_the_user_agent_does_not_reset_the_count(
        self, client, account, settings
    ) -> None:
        """The important half. A lockout keyed on anything the attacker
        controls — User-Agent, a header, a cookie — is not a lockout.
        """
        for index in range(settings.AXES_FAILURE_LIMIT):
            self._fail(client, account, 1, HTTP_USER_AGENT=f"attacker-agent-{index}")

        blocked = _login(client, account.email, PASSWORD, HTTP_USER_AGENT="attacker-agent-final")

        assert blocked.status_code != 200

    def test_a_successful_login_clears_the_count(self, client, account, settings) -> None:
        """AXES_RESET_ON_SUCCESS. Otherwise a user who mistypes twice a day
        eventually locks themselves out for no reason."""
        self._fail(client, account, settings.AXES_FAILURE_LIMIT - 1)

        assert _login(client, account.email, PASSWORD).status_code == 200

        client.post(LOGOUT, content_type="application/json")
        self._fail(client, account, settings.AXES_FAILURE_LIMIT - 1)
        assert _login(client, account.email, PASSWORD).status_code == 200


@pytest.mark.django_db
class TestLogout:
    def test_ends_the_session(self, client, account) -> None:
        _login(client, account.email, PASSWORD)

        response = client.post(LOGOUT, content_type="application/json")

        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_is_harmless_when_not_signed_in(self, client) -> None:
        """Idempotent on purpose: a client retrying after a timeout should not
        get an error for succeeding twice."""
        assert client.post(LOGOUT, content_type="application/json").status_code == 200

    def test_deleting_the_session_row_signs_the_user_out(self, client, account) -> None:
        """The property that justified sessions over JWT (§4.2): revocation is
        one DELETE, effective immediately, not "within fifteen minutes".
        """
        _login(client, account.email, PASSWORD)
        assert "_auth_user_id" in client.session

        Session.objects.all().delete()

        assert "_auth_user_id" not in client.session


@pytest.mark.django_db
class TestCsrfBootstrap:
    def test_issues_a_csrf_cookie(self, client) -> None:
        """The frontend needs a token before it can POST anything.

        Login is deliberately *not* CSRF-exempt: forcing a victim's browser to
        sign in as the attacker is a real attack, and it makes every subsequent
        action attributable to the wrong account.
        """
        response = client.get(CSRF)

        assert response.status_code == 200
        assert "csrftoken" in response.cookies
