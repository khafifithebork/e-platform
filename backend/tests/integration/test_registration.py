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


@pytest.mark.django_db
class TestBetaAdmission:
    """Invitation-only signup, slice 3a.

    **The response must not change between any of these cases.** That is the
    whole control: the endpoint already answers an identical 202 whether an
    address is free or taken (abuse case 1), and admission adds three more
    outcomes — never invited, invited-but-unusable, and invited-and-fine. If any
    of the five is distinguishable, the endpoint becomes an oracle for the
    invitation list.

    An adversarial review of slice 2 noted that this requirement was carried by
    three docstrings and no test. These are the tests.
    """

    @pytest.fixture
    def admin(self):
        from apps.accounts.models import Role
        from apps.accounts.services import create_account

        user = create_account(email="admin@example.test", password=PASSWORD)
        user.role = Role.ADMIN
        user.save(update_fields=["role"])
        return user

    @staticmethod
    def _register(client, email: str):
        return client.post(
            REGISTER, {"email": email, "password": PASSWORD}, content_type="application/json"
        )

    def test_the_flag_is_off_by_default(self, settings) -> None:
        """Merging this must change nothing.

        Slice 3a is a release admission policy, approved for implementation and
        not for deployment. If this default ever flips, every existing
        registration path changes behaviour on merge rather than on a decision.
        """
        assert settings.BETA_INVITATION_REQUIRED is False

    def test_registration_is_unchanged_while_admission_is_off(self, client) -> None:
        # The regression that matters most: with the flag off, an uninvited
        # address registers exactly as it did before slice 3a existed.
        response = self._register(client, "uninvited@example.test")

        assert response.status_code == 202
        assert User.objects.filter(email="uninvited@example.test").exists()
        assert len(mail.outbox) == 1

    def test_invited_registration_succeeds(self, client, settings, admin) -> None:
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import issue_invitation

        settings.BETA_INVITATION_REQUIRED = True
        issue_invitation(actor=admin, email="invited@example.test", reason="cohort one")
        mail.outbox.clear()

        response = self._register(client, "invited@example.test")

        assert response.status_code == 202
        user = User.objects.get(email="invited@example.test")
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["invited@example.test"]

        # The admission was spent, once, and linked to the account it produced.
        invitation = BetaInvitation.objects.get(email="invited@example.test")
        assert invitation.consumed_at is not None
        assert invitation.consumed_by_id == user.pk

    def test_uninvited_registration_creates_no_account(self, client, settings) -> None:
        settings.BETA_INVITATION_REQUIRED = True

        response = self._register(client, "stranger@example.test")

        assert response.status_code == 202
        # Atomic: the account created before the refusal is rolled back, and the
        # verification email is never reached.
        assert not User.objects.filter(email="stranger@example.test").exists()
        assert mail.outbox == []

    @pytest.mark.parametrize("state", ["expired", "revoked", "consumed"])
    def test_an_unusable_invitation_creates_no_account(
        self, client, settings, admin, state
    ) -> None:
        """Expired, revoked and already-spent, each refused and each silent."""
        from datetime import timedelta

        from django.db import transaction
        from django.utils import timezone

        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import consume_invitation, issue_invitation

        email = f"{state}@example.test"
        issue_invitation(actor=admin, email=email, reason="cohort one")

        if state == "expired":
            # Both timestamps move: the check constraint requires
            # expires_at > created_at, so an invitation has to lapse rather than
            # be issued already dead.
            issued = timezone.now() - timedelta(days=40)
            BetaInvitation.objects.filter(email=email).update(
                created_at=issued, expires_at=issued + timedelta(days=30)
            )
        elif state == "revoked":
            from apps.accounts.services import revoke_invitation

            revoke_invitation(actor=admin, email=email, reason="changed my mind")
        else:
            from apps.accounts.services import create_account

            other = create_account(email=email, password=PASSWORD)
            with transaction.atomic():
                consume_invitation(user=other)

        settings.BETA_INVITATION_REQUIRED = True
        mail.outbox.clear()
        existing = set(User.objects.values_list("email", flat=True))

        response = self._register(client, email)

        assert response.status_code == 202
        assert mail.outbox == []
        # No *new* account. The consumed case deliberately already has one.
        assert set(User.objects.values_list("email", flat=True)) == existing

    def test_registration_responses_do_not_reveal_invitation_state(
        self, client, settings, admin
    ) -> None:
        """Five outcomes, one response, byte for byte.

        Invited, never invited, expired, revoked, and an address already
        registered. If any of these differs in status or body, somebody can test
        an address list against this endpoint and learn who is on the beta list.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            create_account,
            issue_invitation,
            revoke_invitation,
        )

        issue_invitation(actor=admin, email="ok@example.test", reason="cohort one")

        issue_invitation(actor=admin, email="lapsed@example.test", reason="cohort one")
        issued = timezone.now() - timedelta(days=40)
        BetaInvitation.objects.filter(email="lapsed@example.test").update(
            created_at=issued, expires_at=issued + timedelta(days=30)
        )

        issue_invitation(actor=admin, email="withdrawn@example.test", reason="cohort one")
        revoke_invitation(actor=admin, email="withdrawn@example.test", reason="no longer")

        create_account(email="taken@example.test", password=PASSWORD)

        settings.BETA_INVITATION_REQUIRED = True

        responses = [
            self._register(client, address)
            for address in (
                "ok@example.test",
                "never@example.test",
                "lapsed@example.test",
                "withdrawn@example.test",
                "taken@example.test",
            )
        ]

        assert {r.status_code for r in responses} == {202}
        assert len({r.content for r in responses}) == 1, [r.content for r in responses]

    @pytest.mark.django_db(transaction=True)
    def test_a_refused_admission_leaves_no_account_under_real_autocommit(
        self, client, settings
    ) -> None:
        """`register_account`'s atomicity, which the ordinary tests cannot see.

        `pytest.mark.django_db` wraps each test in a transaction, so
        `in_atomic_block` is true no matter what the service does — and removing
        `@transaction.atomic` from `register_account` left every other test in
        this class green. Provoked and confirmed before this test existed.

        `transaction=True` restores real autocommit, which is what production
        does. Undecorated, `create_account` would commit on its own and then
        `consume_invitation` would raise `NotTransactional`: a committed account
        for an address that was never admitted, and — because nothing clears
        `consumed_at` and the unique constraint forbids a second invitation row —
        an address that can now neither register nor be invited.
        """
        settings.BETA_INVITATION_REQUIRED = True
        mail.outbox.clear()

        response = self._register(client, "orphan@example.test")

        assert response.status_code == 202
        assert not User.objects.filter(email="orphan@example.test").exists()
        assert mail.outbox == []
