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
    BetaInvitation.objects.filter(pk=invitation.pk).update(consumed_at=consumed_at)
    BetaInvitation.objects.filter(pk=other.pk).update(revoked_at=revoked_at)

    invitation.refresh_from_db()
    other.refresh_from_db()
    assert invitation.consumed_at == consumed_at
    assert invitation.revoked_at is None
    assert other.revoked_at == revoked_at
    assert other.consumed_at is None
    assert not User.objects.exists()
