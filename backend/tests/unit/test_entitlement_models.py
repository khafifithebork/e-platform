"""Entitlement models, and the constraints that hold them true.

Invariant 11 says invariants live in the database, not only in Python
validators. A test asserting that a `CheckConstraint` appears in `Meta` proves
the declaration exists; it does not prove PostgreSQL enforces it, and a
constraint declared but never migrated looks identical in review. So every test
here writes a row the constraint must reject and asserts the database refuses
it — ADR-006 applied to schema.

`.objects.create()` throughout rather than `full_clean()`, deliberately: model
validation is what a serializer would run, and the point is what survives when
something bypasses it.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    if role != Role.STUDENT:
        user.role = role
        user.save(update_fields=["role"])
    return user


@pytest.fixture
def student(db):
    return _user("student@example.test")


@pytest.fixture
def admin(db):
    return _user("admin@example.test", Role.ADMIN)


def _subscription(user, status: str, **overrides):
    from apps.entitlements.models import Subscription, SubscriptionStatus

    now = timezone.now()
    fields = {
        "user": user,
        "status": status,
        "current_period_end": now + timedelta(days=30),
        "provider": "fake",
    }
    if status == SubscriptionStatus.TRIALING:
        fields["trial_end"] = now + timedelta(days=14)
    return Subscription.objects.create(**{**fields, **overrides})


class TestOneLiveSubscriptionPerUser:
    """A second live subscription is double access and, later, double billing.

    Python cannot hold this: two concurrent requests both check "does this user
    already have one?", both see no, both insert. Only a unique index makes the
    second one lose.
    """

    @pytest.mark.parametrize("status", ["TRIALING", "ACTIVE", "PAST_DUE"])
    def test_a_second_live_subscription_is_refused(self, student, status) -> None:
        _subscription(student, status)

        # Matched by name: asserting IntegrityError alone would pass if some
        # *other* constraint refused the row, which would leave this one
        # untested while looking green.
        with pytest.raises(IntegrityError, match="one_live_subscription_per_user"):
            _subscription(student, status)

    def test_two_different_users_may_each_have_one(self, student) -> None:
        other = _user("other@example.test")

        _subscription(student, "ACTIVE")
        _subscription(other, "ACTIVE")  # must not raise

    def test_a_canceled_row_does_not_block_resubscribing(self, student) -> None:
        """CANCELED still grants access until the period ends, so the row has
        to survive alongside a fresh subscription. Excluding it from the
        constraint is what makes resubscribe-before-expiry possible — and is
        why the resolver must consider every subscription, not assume one."""
        _subscription(student, "CANCELED")

        _subscription(student, "ACTIVE")  # must not raise

    def test_an_expired_row_does_not_block_resubscribing(self, student) -> None:
        _subscription(student, "EXPIRED")

        _subscription(student, "ACTIVE")  # must not raise


class TestTrialingImpliesATrialEnd:
    def test_trialing_without_a_trial_end_is_refused(self, student) -> None:
        """A trial with no end never expires. The resolver would read
        `trial_end is None` and have no boundary to compare against, so the
        row has to be impossible rather than handled."""
        with pytest.raises(IntegrityError, match="trialing_requires_a_trial_end"):
            _subscription(student, "TRIALING", trial_end=None)

    def test_a_non_trial_may_have_no_trial_end(self, student) -> None:
        _subscription(student, "ACTIVE", trial_end=None)  # must not raise


class TestProviderIdentityIsUniquePerProvider:
    def test_the_same_provider_id_twice_is_refused(self, student) -> None:
        """M8 looks a subscription up by the provider's id when a webhook
        arrives. Two rows sharing one would make that lookup ambiguous at
        exactly the moment money is involved."""
        other = _user("other@example.test")
        _subscription(student, "ACTIVE", provider_subscription_id="sub_1")

        with pytest.raises(IntegrityError, match="subscription_unique_per_provider_id"):
            _subscription(other, "ACTIVE", provider_subscription_id="sub_1")

    def test_many_rows_may_have_no_provider_id(self, student) -> None:
        """Null until M8 attaches a real provider. NULLs must not collide, or
        the second unbilled subscription in the system fails to insert."""
        other = _user("other@example.test")

        _subscription(student, "ACTIVE", provider_subscription_id=None)
        _subscription(other, "ACTIVE", provider_subscription_id=None)


class TestOverridesAreTimeBounded:
    def _override(self, user, granted_by, *, starts_at, ends_at):
        from apps.entitlements.models import AccessOverride

        return AccessOverride.objects.create(
            user=user,
            granted_by=granted_by,
            reason="Support goodwill.",
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def test_an_override_ending_before_it_starts_is_refused(self, student, admin) -> None:
        now = timezone.now()

        with pytest.raises(IntegrityError, match="override_ends_after_it_starts"):
            self._override(student, admin, starts_at=now, ends_at=now - timedelta(days=1))

    def test_an_override_ending_exactly_when_it_starts_is_refused(self, student, admin) -> None:
        """Zero duration grants nothing and is more likely a bug than intent."""
        now = timezone.now()

        with pytest.raises(IntegrityError, match="override_ends_after_it_starts"):
            self._override(student, admin, starts_at=now, ends_at=now)

    def test_an_override_must_have_a_reason(self, student, admin) -> None:
        """§5.2's whole argument for a table over a boolean is that the grant
        explains itself. A blank reason is the boolean again, with extra
        columns."""
        now = timezone.now()

        from apps.entitlements.models import AccessOverride

        with pytest.raises(IntegrityError, match="override_requires_a_reason"):
            AccessOverride.objects.create(
                user=student,
                granted_by=admin,
                reason="",
                starts_at=now,
                ends_at=now + timedelta(days=7),
            )

    def test_a_user_may_hold_several_overrides_over_time(self, student, admin) -> None:
        now = timezone.now()

        self._override(student, admin, starts_at=now - timedelta(days=30), ends_at=now)
        self._override(student, admin, starts_at=now, ends_at=now + timedelta(days=30))


class TestTheGrantorIsNotErasable:
    def test_deleting_the_granting_admin_is_refused(self, student, admin) -> None:
        """PROTECT, like every other actor reference in this codebase (§5.4).
        An override whose grantor vanished is an unexplained grant, which is
        precisely what the table exists to prevent."""
        from django.db.models import ProtectedError

        from apps.entitlements.models import AccessOverride

        now = timezone.now()
        AccessOverride.objects.create(
            user=student,
            granted_by=admin,
            reason="Support goodwill.",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )

        with pytest.raises(ProtectedError):
            admin.delete()


class TestSubscriptionEventsAreAnAppendOnlyLog:
    def test_an_event_records_the_transition_it_describes(self, student) -> None:
        from apps.entitlements.models import SubscriptionEvent

        subscription = _subscription(student, "ACTIVE")

        event = SubscriptionEvent.objects.create(
            subscription=subscription,
            event_type=SubscriptionEvent.EventType.ACTIVATED,
            from_status="TRIALING",
            to_status="ACTIVE",
        )

        assert event.subscription == subscription

    def test_events_survive_being_read_newest_first(self, student) -> None:
        """Ordering is the whole point of a diagnostic log: "what happened to
        this person, most recently first"."""
        from apps.entitlements.models import SubscriptionEvent

        subscription = _subscription(student, "ACTIVE")
        for event_type in ("TRIAL_STARTED", "ACTIVATED", "PAYMENT_FAILED"):
            SubscriptionEvent.objects.create(subscription=subscription, event_type=event_type)

        newest = SubscriptionEvent.objects.filter(subscription=subscription).first()

        assert newest.event_type == "PAYMENT_FAILED"
