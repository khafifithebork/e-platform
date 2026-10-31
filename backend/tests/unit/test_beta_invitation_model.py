"""Database backstops for beta invitations, before admission services exist."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

pytestmark = pytest.mark.django_db


def test_invitation_email_is_case_insensitively_unique() -> None:
    from apps.accounts.models import BetaInvitation

    original = BetaInvitation.objects.create(
        email="Invited@example.test", expires_at=timezone.now() + timedelta(days=2)
    )

    # Direct writes bypass the forthcoming invitation service's normalization.
    with pytest.raises(IntegrityError), transaction.atomic():
        BetaInvitation.objects.create(
            email="invited@example.test", expires_at=timezone.now() + timedelta(days=3)
        )

    assert BetaInvitation.objects.count() == 1
    original.refresh_from_db()
    assert original.email == "Invited@example.test"


@pytest.mark.parametrize("offset_seconds", [-1, 0])
def test_expiry_must_follow_issue_time(offset_seconds: int) -> None:
    from apps.accounts.models import BetaInvitation

    invitation = BetaInvitation.objects.create(
        email="invited@example.test", expires_at=timezone.now() + timedelta(days=2)
    )
    original_expiry = invitation.expires_at

    with pytest.raises(IntegrityError), transaction.atomic():
        BetaInvitation.objects.filter(pk=invitation.pk).update(
            expires_at=F("created_at") + timedelta(seconds=offset_seconds)
        )

    invitation.refresh_from_db()
    assert invitation.expires_at == original_expiry


def test_invalid_expiry_is_rejected_on_insert() -> None:
    from apps.accounts.models import BetaInvitation

    with pytest.raises(IntegrityError), transaction.atomic():
        BetaInvitation.objects.create(
            email="invited@example.test", expires_at=timezone.now() - timedelta(seconds=1)
        )

    assert not BetaInvitation.objects.exists()


def test_invitation_records_lifecycle_without_creating_an_account() -> None:
    from apps.accounts.models import BetaInvitation, User

    invitation = BetaInvitation.objects.create(
        email="invited@example.test", expires_at=timezone.now() + timedelta(days=2)
    )
    other = BetaInvitation.objects.create(
        email="another@example.test", expires_at=timezone.now() + timedelta(days=2)
    )
    consumed_at = timezone.now()
    revoked_at = timezone.now()

    # Consumption needs an account to point at, since slice 2 added `consumed_by`
    # and a constraint that the two columns move together — a row recording that
    # somebody was admitted without recording who is a bug, not a state.
    #
    # **This test's point survives the change and is now sharper.** It was
    # `assert not User.objects.exists()`, demonstrating that the invitation
    # machinery creates no account. A consumed invitation necessarily references
    # one, so the claim becomes: consuming creates no account *of its own* — the
    # only user here is the one this test made.
    consumer = User.objects.create_user(
        email="invited@example.test", password="a-long-enough-passphrase"
    )
    BetaInvitation.objects.filter(pk=invitation.pk).update(
        consumed_at=consumed_at, consumed_by=consumer
    )
    BetaInvitation.objects.filter(pk=other.pk).update(revoked_at=revoked_at)

    invitation.refresh_from_db()
    other.refresh_from_db()
    assert invitation.consumed_at == consumed_at
    assert invitation.consumed_by_id == consumer.pk
    assert invitation.revoked_at is None
    assert other.revoked_at == revoked_at
    assert other.consumed_at is None
    # Revocation still needs nobody, which is the asymmetry worth keeping visible.
    assert other.consumed_by is None
    assert list(User.objects.values_list("pk", flat=True)) == [consumer.pk]
