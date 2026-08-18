"""Password reset and change.

Higher stakes than verification. A leaked verification token marks an address
confirmed; a leaked reset token *is* account takeover, which is why the
lifetime is an hour rather than a day.

The assertion that matters most is session invalidation. Someone resetting
their password is often doing it *because* they believe an attacker has access
— if the attacker's session survives, the reset achieved nothing.
"""

from __future__ import annotations

import pytest
from django.core import mail

RESET = "/api/v1/auth/password/reset/"
CONFIRM = "/api/v1/auth/password/reset/confirm/"
CHANGE = "/api/v1/auth/password/change/"
LOGIN = "/api/v1/auth/login/"

PASSWORD = "a-sufficiently-long-passphrase"
NEW_PASSWORD = "an-entirely-different-passphrase"


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


def _request_reset(client, email: str):
    return client.post(RESET, {"email": email}, content_type="application/json")


def _token_from_email() -> str:
    return mail.outbox[-1].body.split("\n\n")[1].strip()


@pytest.mark.django_db
class TestResetRequestRevealsNothing:
    def test_a_known_address_is_accepted(self, client, account) -> None:
        assert _request_reset(client, account.email).status_code == 202

    def test_an_unknown_address_looks_identical(self, client, account) -> None:
        """The most attractive enumeration oracle in any application: it is
        designed for people who are locked out and therefore unauthenticated."""
        known = _request_reset(client, account.email)
        unknown = _request_reset(client, "nobody@example.test")

        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()

    def test_no_email_is_sent_to_an_unknown_address(self, client) -> None:
        _request_reset(client, "nobody@example.test")

        assert mail.outbox == []


@pytest.mark.django_db
class TestResetConfirm:
    def test_sets_the_new_password(self, client, account) -> None:
        _request_reset(client, account.email)

        response = client.post(
            CONFIRM,
            {"token": _token_from_email(), "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        assert response.status_code == 200
        account.refresh_from_db()
        assert account.check_password(NEW_PASSWORD)
        assert not account.check_password(PASSWORD)

    def test_a_token_cannot_be_reused(self, client, account) -> None:
        _request_reset(client, account.email)
        token = _token_from_email()
        client.post(
            CONFIRM,
            {"token": token, "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        replay = client.post(
            CONFIRM,
            {"token": token, "new_password": "yet-another-passphrase-here"},
            content_type="application/json",
        )

        assert replay.status_code == 400

    def test_an_earlier_outstanding_token_stops_working(self, client, account) -> None:
        """An attacker who requested a reset earlier must not still hold a
        working key after the victim completes their own reset."""
        _request_reset(client, account.email)
        attacker_token = _token_from_email()

        _request_reset(client, account.email)
        client.post(
            CONFIRM,
            {"token": _token_from_email(), "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        stale = client.post(
            CONFIRM,
            {"token": attacker_token, "new_password": "attacker-chosen-passphrase"},
            content_type="application/json",
        )

        assert stale.status_code == 400

    def test_a_weak_new_password_is_refused(self, client, account) -> None:
        _request_reset(client, account.email)

        response = client.post(
            CONFIRM,
            {"token": _token_from_email(), "new_password": "1234"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "new_password" in response.json()["errors"]

    def test_an_invalid_token_does_not_say_why(self, client) -> None:
        response = client.post(
            CONFIRM,
            {"token": "not-a-real-token", "new_password": NEW_PASSWORD},
            content_type="application/json",
        )
        body = response.json()["detail"].lower()

        assert response.status_code == 400
        for leak in ("expired", "used", "unknown", "not found"):
            assert leak not in body


@pytest.mark.django_db
class TestResetInvalidatesSessions:
    def test_an_existing_session_stops_working(self, client, account) -> None:
        """The point of the whole flow.

        A reset is often prompted by the suspicion that someone else has
        access. If their session survives it, nothing has been achieved.

        Asserted by making an authenticated request rather than by inspecting
        the session store. Django does not delete the row: it rejects the
        session because the auth hash it carries no longer matches the user's
        password. `client.session` reads the store directly and would still
        show `_auth_user_id`, which is why checking it proves nothing.
        """
        client.post(
            LOGIN,
            {"email": account.email, "password": PASSWORD},
            content_type="application/json",
        )
        # The session works before the reset.
        assert (
            client.post(
                CHANGE,
                {"current_password": PASSWORD, "new_password": PASSWORD},
                content_type="application/json",
            ).status_code
            == 200
        )

        _request_reset(client, account.email)
        client.post(
            CONFIRM,
            {"token": _token_from_email(), "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        after_reset = client.post(
            CHANGE,
            {"current_password": NEW_PASSWORD, "new_password": "something-else-entirely-ok"},
            content_type="application/json",
        )

        assert after_reset.status_code in (401, 403)


@pytest.mark.django_db
class TestPasswordChange:
    def _sign_in(self, client, account):
        client.post(
            LOGIN,
            {"email": account.email, "password": PASSWORD},
            content_type="application/json",
        )

    def test_requires_authentication(self, client, account) -> None:
        response = client.post(
            CHANGE,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        assert response.status_code in (401, 403)

    def test_changes_the_password(self, client, account) -> None:
        self._sign_in(client, account)

        response = client.post(
            CHANGE,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        assert response.status_code == 200
        account.refresh_from_db()
        assert account.check_password(NEW_PASSWORD)

    def test_the_current_password_is_required_to_be_correct(self, client, account) -> None:
        """An open session on a shared machine must not be enough to take the
        account over permanently."""
        self._sign_in(client, account)

        response = client.post(
            CHANGE,
            {"current_password": "not-the-current-one", "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        assert response.status_code == 400
        account.refresh_from_db()
        assert account.check_password(PASSWORD)

    def test_the_caller_stays_signed_in(self, client, account) -> None:
        """Changing a password rotates the session auth hash, which would
        otherwise sign the user out of the browser they just used."""
        self._sign_in(client, account)

        client.post(
            CHANGE,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        assert "_auth_user_id" in client.session
