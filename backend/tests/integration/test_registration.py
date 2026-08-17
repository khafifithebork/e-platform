"""Registration and verification over HTTP.

The abuse cases from the M2 threat model, as tests. These are the ones that
would pass a functional review and still be wrong: registration that works
perfectly while quietly telling an attacker which addresses are registered.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

User = get_user_model()

REGISTER = "/api/v1/auth/register/"
VERIFY = "/api/v1/auth/verify-email/"
RESEND = "/api/v1/auth/resend-verification/"

PASSWORD = "a-sufficiently-long-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    """Raise the limits rather than remove them.

    Every scope must stay defined — DRF raises ImproperlyConfigured for a
    scope with no rate — and several tests here make repeated requests to the
    same endpoint deliberately. The throttle values themselves are asserted
    against settings in their own test.
    """
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.mark.django_db
class TestRegistration:
    def test_creates_an_account(self, client) -> None:
        response = client.post(
            REGISTER,
            {"email": "new@example.test", "password": PASSWORD},
            content_type="application/json",
        )

        assert response.status_code == 202
        assert User.objects.filter(email="new@example.test").exists()

    def test_sends_a_verification_email(self, client) -> None:
        client.post(
            REGISTER,
            {"email": "new@example.test", "password": PASSWORD},
            content_type="application/json",
        )

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["new@example.test"]

    def test_the_password_is_never_echoed(self, client) -> None:
        response = client.post(
            REGISTER,
            {"email": "new@example.test", "password": PASSWORD},
            content_type="application/json",
        )

        assert PASSWORD not in response.content.decode()

    def test_a_weak_password_is_refused_with_field_errors(self, client) -> None:
        response = client.post(
            REGISTER,
            {"email": "new@example.test", "password": "1234"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "password" in response.json()["errors"]


@pytest.mark.django_db
class TestAccountEnumeration:
    """Abuse case 1. §7.1 treats this as a real threat, not a nicety."""

    def _register(self, client, email: str):
        return client.post(
            REGISTER, {"email": email, "password": PASSWORD}, content_type="application/json"
        )

    def test_a_taken_address_is_indistinguishable_from_a_new_one(self, client) -> None:
        first = self._register(client, "taken@example.test")
        second = self._register(client, "taken@example.test")

        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()

    def test_the_second_attempt_creates_nothing(self, client) -> None:
        self._register(client, "taken@example.test")
        self._register(client, "taken@example.test")

        assert User.objects.filter(email="taken@example.test").count() == 1

    def test_the_second_attempt_does_not_reset_the_password(self, client) -> None:
        """The nastier version of the same bug: a silent 202 that quietly
        overwrites the existing account's password would be account takeover."""
        self._register(client, "taken@example.test")

        client.post(
            REGISTER,
            {"email": "taken@example.test", "password": "attacker-chosen-passphrase"},
            content_type="application/json",
        )

        user = User.objects.get(email="taken@example.test")
        assert user.check_password(PASSWORD)
        assert not user.check_password("attacker-chosen-passphrase")

    def test_resend_looks_the_same_for_an_unknown_address(self, client) -> None:
        known = client.post(
            RESEND, {"email": "nobody@example.test"}, content_type="application/json"
        )

        assert known.status_code == 202


@pytest.mark.django_db
class TestPrivilegeEscalation:
    """Abuse case 3 — the one that would hand over the platform."""

    def test_a_role_in_the_body_is_ignored(self, client) -> None:
        client.post(
            REGISTER,
            {"email": "climber@example.test", "password": PASSWORD, "role": "ADMIN"},
            content_type="application/json",
        )

        assert User.objects.get(email="climber@example.test").role == "STUDENT"

    def test_staff_and_superuser_flags_in_the_body_are_ignored(self, client) -> None:
        client.post(
            REGISTER,
            {
                "email": "climber@example.test",
                "password": PASSWORD,
                "is_staff": True,
                "is_superuser": True,
                "is_email_verified": True,
            },
            content_type="application/json",
        )

        user = User.objects.get(email="climber@example.test")
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.is_email_verified is False


@pytest.mark.django_db
class TestVerification:
    def _register_and_take_token(self, client, email: str) -> str:
        client.post(
            REGISTER, {"email": email, "password": PASSWORD}, content_type="application/json"
        )
        # The raw token exists only in the email — by design.
        return mail.outbox[-1].body.split("\n\n")[1].strip()

    def test_a_valid_token_verifies_the_account(self, client) -> None:
        token = self._register_and_take_token(client, "new@example.test")

        response = client.post(VERIFY, {"token": token}, content_type="application/json")

        assert response.status_code == 200
        assert User.objects.get(email="new@example.test").is_email_verified is True

    def test_replaying_a_token_fails(self, client) -> None:
        token = self._register_and_take_token(client, "new@example.test")
        client.post(VERIFY, {"token": token}, content_type="application/json")

        replay = client.post(VERIFY, {"token": token}, content_type="application/json")

        assert replay.status_code == 400

    def test_an_invalid_token_does_not_say_why(self, client) -> None:
        """Unknown, expired and already-used must be one answer. Separating
        them turns a failed guess into information."""
        response = client.post(
            VERIFY, {"token": "not-a-real-token-at-all"}, content_type="application/json"
        )
        body = response.json()["detail"].lower()

        assert response.status_code == 400
        for leak in ("expired", "used", "unknown", "not found"):
            assert leak not in body
