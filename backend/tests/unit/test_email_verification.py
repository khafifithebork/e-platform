"""Email verification tokens.

`architecture.md` §10 M2 lists "storing the verification token instead of its
hash" as a common mistake, and it is the one that matters most here: a token in
the database is a bearer credential, so a read-only leak — a backup, a log, an
errant admin query — hands over every pending account.

The token is therefore treated exactly like a password. The raw value exists
only in transit; the database stores a hash of it.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


@pytest.fixture
def user(db):
    from apps.accounts.services import create_account

    return create_account(email="learner@example.test", password="pw-for-this-test")


@pytest.mark.django_db
class TestTokenIssuance:
    def test_returns_a_raw_token_to_send_by_email(self, user) -> None:
        from apps.accounts.services import issue_email_verification

        raw = issue_email_verification(user=user)

        assert isinstance(raw, str)
        assert raw

    def test_the_raw_token_is_never_stored(self, user) -> None:
        """The whole point. A leak of the table must not yield usable tokens."""
        from apps.accounts.models import EmailVerificationToken
        from apps.accounts.services import issue_email_verification

        raw = issue_email_verification(user=user)

        assert not EmailVerificationToken.objects.filter(token_hash=raw).exists()
        stored = EmailVerificationToken.objects.get(user=user)
        assert stored.token_hash != raw

    def test_tokens_have_enough_entropy_to_resist_guessing(self, user) -> None:
        """Short tokens are enumerable, and there is no lockout on a token
        endpoint the way there is on login."""
        from apps.accounts.services import issue_email_verification

        assert len(issue_email_verification(user=user)) >= 32

    def test_two_issues_produce_different_tokens(self, user) -> None:
        from apps.accounts.services import issue_email_verification

        assert issue_email_verification(user=user) != issue_email_verification(user=user)

    def test_the_token_expires(self, user) -> None:
        from apps.accounts.models import EmailVerificationToken
        from apps.accounts.services import issue_email_verification

        issue_email_verification(user=user)
        stored = EmailVerificationToken.objects.filter(user=user).latest("created_at")

        assert stored.expires_at > timezone.now()


@pytest.mark.django_db
class TestVerification:
    def test_a_valid_token_verifies_the_account(self, user) -> None:
        from apps.accounts.services import issue_email_verification, verify_email

        raw = issue_email_verification(user=user)
        verified = verify_email(token=raw)

        verified.refresh_from_db()
        assert verified.pk == user.pk
        assert verified.is_email_verified is True

    def test_a_token_cannot_be_used_twice(self, user) -> None:
        """Abuse case 4. A verification link sits in an inbox forever and gets
        forwarded; replaying it must do nothing."""
        from apps.accounts.services import (
            InvalidVerificationToken,
            issue_email_verification,
            verify_email,
        )

        raw = issue_email_verification(user=user)
        verify_email(token=raw)

        with pytest.raises(InvalidVerificationToken):
            verify_email(token=raw)

    def test_an_expired_token_is_refused(self, user) -> None:
        """Abuse case 5."""
        from datetime import timedelta

        from apps.accounts.models import EmailVerificationToken
        from apps.accounts.services import (
            InvalidVerificationToken,
            issue_email_verification,
            verify_email,
        )

        raw = issue_email_verification(user=user)
        EmailVerificationToken.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        with pytest.raises(InvalidVerificationToken):
            verify_email(token=raw)

    def test_an_unknown_token_is_refused(self, user) -> None:
        from apps.accounts.services import InvalidVerificationToken, verify_email

        with pytest.raises(InvalidVerificationToken):
            verify_email(token="not-a-real-token-value-at-all-here")

    def test_an_empty_token_is_refused(self, user) -> None:
        """Guards against a lookup that matches the hash of the empty string."""
        from apps.accounts.services import InvalidVerificationToken, verify_email

        with pytest.raises(InvalidVerificationToken):
            verify_email(token="")

    def test_a_failed_verification_leaves_the_account_unverified(self, user) -> None:
        from apps.accounts.services import InvalidVerificationToken, verify_email

        with pytest.raises(InvalidVerificationToken):
            verify_email(token="wrong-token-entirely-and-long-enough")

        user.refresh_from_db()
        assert user.is_email_verified is False

    def test_one_users_token_cannot_verify_another(self, user) -> None:
        """The token identifies the account; nothing else is trusted."""
        from apps.accounts.services import create_account, issue_email_verification, verify_email

        other = create_account(email="other@example.test", password="pw-for-this-test")
        raw = issue_email_verification(user=other)

        verified = verify_email(token=raw)

        assert verified.pk == other.pk
        user.refresh_from_db()
        assert user.is_email_verified is False
