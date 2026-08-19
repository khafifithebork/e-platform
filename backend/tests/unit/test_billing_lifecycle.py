"""The fake provider and the subscription state machine.

Driven through the management command wherever possible, because that is the
whole interface M4 has for moving a subscription — CLAUDE.md §6 forbids
mocking our own service layer and asserting it was called, so these run the
real adapter against the real services and assert on what the database ends up
believing.

The tests worth reading twice are `TestTheProviderNeverWritesRows` and
`TestTransitionsNotInTheTableAreRefused`. The first pins the adapter boundary
that makes M8 a swap rather than a rewrite; the second is the equivalent of
M3's publish guard — a state change absent from the table must be impossible,
not merely unused.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str = "student@example.test"):
    from apps.accounts.services import create_account

    return create_account(email=email, password=PASSWORD)


def _billing(action: str, email: str, **flags) -> str:
    out = StringIO()
    call_command("billing", action, email=email, stdout=out, **flags)
    return out.getvalue()


@pytest.fixture
def student(db):
    return _user()


def _subscription_of(user):
    from apps.entitlements.models import Subscription

    return Subscription.objects.filter(user=user).order_by("-created_at").first()


class TestStarting:
    def test_starting_without_a_trial_is_active(self, student) -> None:
        _billing("start", student.email)

        subscription = _subscription_of(student)
        assert subscription.status == "ACTIVE"
        assert subscription.trial_end is None
        assert subscription.provider == "fake"
        assert subscription.provider_subscription_id.startswith("fake_")

    def test_starting_with_a_trial_is_trialing_and_bounded(self, student) -> None:
        _billing("start", student.email, trial_days=14)

        subscription = _subscription_of(student)
        assert subscription.status == "TRIALING"
        assert subscription.trial_end is not None
        # The trial and the period end together. Two different answers to
        # "when does this end" is how a resolver grants access it should not.
        assert subscription.current_period_end == subscription.trial_end

    def test_a_second_start_is_refused_with_a_readable_error(self, student) -> None:
        _billing("start", student.email)

        with pytest.raises(CommandError, match="already has a live subscription"):
            _billing("start", student.email)

    def test_an_unknown_email_is_refused(self, db) -> None:
        with pytest.raises(CommandError, match="No user with email"):
            _billing("start", "nobody@example.test")


class TestTheLifecycle:
    def test_a_trial_converts_to_active(self, student) -> None:
        _billing("start", student.email, trial_days=14)

        _billing("renew", student.email)

        assert _subscription_of(student).status == "ACTIVE"

    def test_a_failed_payment_does_not_move_the_period_end(self, student) -> None:
        """The grace period decides whether PAST_DUE still grants access.
        Extending the period end would grant free access; setting it to now
        would end access instantly and make the grace period unreachable."""
        _billing("start", student.email)
        before = _subscription_of(student).current_period_end

        _billing("fail-payment", student.email)

        subscription = _subscription_of(student)
        assert subscription.status == "PAST_DUE"
        assert subscription.current_period_end == before

    def test_a_failed_payment_can_recover(self, student) -> None:
        _billing("start", student.email)
        _billing("fail-payment", student.email)

        _billing("renew", student.email)

        assert _subscription_of(student).status == "ACTIVE"

    def test_cancelling_keeps_access_until_the_period_ends(self, student) -> None:
        """The customer paid for the period. Ending access at cancellation
        would be taking back something already bought."""
        _billing("start", student.email)

        _billing("cancel", student.email)

        subscription = _subscription_of(student)
        assert subscription.status == "CANCELED"
        assert subscription.cancel_at_period_end is True
        assert subscription.current_period_end > timezone.now()

    def test_cancelling_immediately_ends_access_now(self, student) -> None:
        _billing("start", student.email)

        _billing("cancel", student.email, immediately=True)

        subscription = _subscription_of(student)
        assert subscription.status == "EXPIRED"
        assert subscription.current_period_end <= timezone.now()


class TestTransitionsNotInTheTableAreRefused:
    """M3's publish guard, applied to money.

    A transition absent from ALLOWED_TRANSITIONS must be impossible rather
    than merely unused, because the ones that are missing are missing for a
    reason — an EXPIRED subscription that could return to ACTIVE without a
    payment is free access granted by a state change nobody would test.
    """

    def test_an_expired_subscription_cannot_be_renewed(self, student) -> None:
        """Through the command this is stopped by the liveness check, one step
        before the transition table — matched by message so the test says which
        control refused it. The table itself is provoked directly below,
        because a guard only reachable past another guard is a guard nothing
        tests."""
        _billing("start", student.email)
        _billing("cancel", student.email, immediately=True)

        with pytest.raises(CommandError, match="no live subscription"):
            _billing("renew", student.email)

        assert _subscription_of(student).status == "EXPIRED"

    def test_the_transition_table_refuses_expired_to_active(self, student) -> None:
        """Called at the service layer, bypassing the liveness check, because
        that is the only way to reach this branch. If EXPIRED could return to
        ACTIVE without a payment, that is free access granted by a state change
        nobody would think to test."""
        from apps.entitlements import services
        from apps.entitlements.providers.fake import FakeBillingProvider

        _billing("start", student.email)
        _billing("cancel", student.email, immediately=True)
        expired = _subscription_of(student)

        with pytest.raises(services.SubscriptionTransitionError, match="EXPIRED -> ACTIVE"):
            services.renew(subscription=expired, provider=FakeBillingProvider())

        expired.refresh_from_db()
        assert expired.status == "EXPIRED"

    def test_the_transition_table_refuses_expired_to_past_due(self, student) -> None:
        from apps.entitlements import services
        from apps.entitlements.providers.fake import FakeBillingProvider

        _billing("start", student.email)
        _billing("cancel", student.email, immediately=True)
        expired = _subscription_of(student)

        with pytest.raises(services.SubscriptionTransitionError):
            services.fail_payment(subscription=expired, provider=FakeBillingProvider())

    def test_acting_on_a_user_with_no_subscription_is_refused(self, student) -> None:
        with pytest.raises(CommandError, match="no live subscription"):
            _billing("renew", student.email)

    def test_a_cancelled_subscription_cannot_be_renewed(self, student) -> None:
        """CANCELED is not live, so there is nothing for renew to act on.
        Resubscribing means starting a new subscription, which the model
        allows alongside the cancelled row."""
        _billing("start", student.email)
        _billing("cancel", student.email)

        with pytest.raises(CommandError, match="no live subscription"):
            _billing("renew", student.email)


class TestEveryChangeIsOnTheRecord:
    def test_the_log_reads_as_a_history(self, student) -> None:
        from apps.entitlements.models import SubscriptionEvent

        _billing("start", student.email, trial_days=14)
        _billing("renew", student.email)
        _billing("fail-payment", student.email)
        _billing("cancel", student.email)

        events = list(
            SubscriptionEvent.objects.filter(subscription=_subscription_of(student))
            .order_by("created_at")
            .values_list("event_type", flat=True)
        )

        assert events == [
            "TRIAL_STARTED",
            "RENEWED",
            "PAYMENT_FAILED",
            "CANCELLATION_REQUESTED",
        ]

    def test_a_refused_transition_records_nothing(self, student) -> None:
        """A rejected attempt in the log makes the history a lie."""
        from apps.entitlements.models import SubscriptionEvent

        _billing("start", student.email)
        _billing("cancel", student.email, immediately=True)
        before = SubscriptionEvent.objects.count()

        with pytest.raises(CommandError):
            _billing("renew", student.email)

        assert SubscriptionEvent.objects.count() == before

    def test_the_provider_payload_is_kept_verbatim(self, student) -> None:
        """Never parsed to make a decision — kept so a support question six
        weeks later has something to read."""
        from apps.entitlements.models import SubscriptionEvent

        _billing("start", student.email)

        event = SubscriptionEvent.objects.get(subscription=_subscription_of(student))
        assert event.provider_payload["event"] == "subscription.started"


class TestTheProviderNeverWritesRows:
    """The adapter boundary that makes M8 a swap rather than a rewrite.

    Invariant 4. If an adapter can write a row, entitlement logic will
    eventually be written inside it, which is the failure CLAUDE.md §10
    describes as access rules inside a webhook handler.
    """

    def test_calling_every_provider_method_creates_nothing(self, db) -> None:
        from apps.entitlements.models import Subscription, SubscriptionEvent
        from apps.entitlements.providers.fake import FakeBillingProvider

        provider = FakeBillingProvider()
        now = timezone.now()

        snapshot = provider.start_subscription(reference="whoever", trial_days=7)
        provider.renew_subscription(provider_subscription_id=snapshot.provider_subscription_id)
        provider.fail_payment(
            provider_subscription_id=snapshot.provider_subscription_id,
            current_period_end=now + timedelta(days=30),
        )
        provider.cancel_subscription(provider_subscription_id=snapshot.provider_subscription_id)

        assert not Subscription.objects.exists()
        assert not SubscriptionEvent.objects.exists()

    def test_the_fake_satisfies_the_declared_interface(self) -> None:
        """A protocol nothing is checked against is documentation, not a
        contract — and M8's adapter has to satisfy the same one."""
        from apps.entitlements.providers.base import BillingProvider
        from apps.entitlements.providers.fake import FakeBillingProvider

        assert isinstance(FakeBillingProvider(), BillingProvider)

    def test_the_snapshot_carries_no_money(self) -> None:
        """M4 does not model billing. A price appearing on this dataclass is
        the moment that stopped being true."""
        import dataclasses

        from apps.entitlements.providers.base import ProviderSubscription

        names = {f.name for f in dataclasses.fields(ProviderSubscription)}

        assert not names & {"amount", "currency", "price", "price_id", "interval", "invoice"}


class TestExpiry:
    """The state time produces. No provider call: a period ending is something
    we observe, not something a provider tells us."""

    def test_a_cancelled_subscription_expires(self, student) -> None:
        _billing("start", student.email)
        _billing("cancel", student.email)

        from apps.entitlements.models import Subscription
        from apps.entitlements.services import expire

        cancelled = Subscription.objects.get(user=student.pk)
        expire(subscription=cancelled)

        cancelled.refresh_from_db()
        assert cancelled.status == "EXPIRED"

    def test_expiring_records_the_transition(self, student) -> None:
        from apps.entitlements.models import Subscription, SubscriptionEvent
        from apps.entitlements.services import expire

        _billing("start", student.email)
        expire(subscription=Subscription.objects.get(user=student.pk))

        event = SubscriptionEvent.objects.filter(event_type="EXPIRED").get()
        assert event.from_status == "ACTIVE"
        assert event.to_status == "EXPIRED"

    def test_an_already_expired_subscription_cannot_expire_again(self, student) -> None:
        """Not in the transition table. A second EXPIRED event would put a
        transition on the record that never happened."""
        from apps.entitlements import services
        from apps.entitlements.models import Subscription

        _billing("start", student.email)
        _billing("cancel", student.email, immediately=True)
        expired = Subscription.objects.get(user=student.pk)

        with pytest.raises(services.SubscriptionTransitionError, match="EXPIRED -> EXPIRED"):
            services.expire(subscription=expired)

    def test_the_expire_command_works_end_to_end(self, student) -> None:
        _billing("start", student.email)

        _billing("expire", student.email)

        assert _subscription_of(student).status == "EXPIRED"
