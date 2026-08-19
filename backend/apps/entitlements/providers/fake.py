"""A billing provider that charges nobody.

This exists so that M4 can be built and fully tested before a payment provider
is chosen (CLAUDE.md §10). Building entitlement first means billing later
becomes a thin event source feeding a system that already works; building
payments first means entitlement gets written inside webhook handlers, which
is how it ends up implemented three times.

It is a **real adapter**, not a mock. CLAUDE.md §6 forbids mocking our own
service layer and asserting it was called — that tests nothing. Tests drive
this provider through the same interface M8's will implement, and assert on
what the database ends up believing.

It is also deliberately dumb: it holds no state of its own and reads nothing.
Each call computes a snapshot from the arguments and the clock. Real providers
are the authority on their own subscriptions; this one has no authority to
model, so it invents the minimum that lets our side be exercised.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.utils import timezone

from apps.entitlements.providers.base import ProviderSubscription

# Thirty days is the fake's billing period. It is not a product decision — the
# real interval comes from the provider in M8 — it just has to be long enough
# that "the period has not ended" is the interesting case in a test.
PERIOD = timedelta(days=30)


class FakeBillingProvider:
    """In-memory, deterministic, and free."""

    name = "fake"

    def _snapshot(
        self,
        *,
        provider_subscription_id: str,
        status: str,
        current_period_end,
        trial_end=None,
        cancel_at_period_end: bool = False,
        event: str,
    ) -> ProviderSubscription:
        return ProviderSubscription(
            provider=self.name,
            provider_subscription_id=provider_subscription_id,
            status=status,
            current_period_end=current_period_end,
            trial_end=trial_end,
            cancel_at_period_end=cancel_at_period_end,
            raw={"event": event, "at": timezone.now().isoformat()},
        )

    def start_subscription(
        self, *, reference: str, trial_days: int | None = None
    ) -> ProviderSubscription:
        now = timezone.now()

        if trial_days is not None:
            trial_end = now + timedelta(days=trial_days)
            # The period ends when the trial does. A trial that outlives its
            # own period, or vice versa, gives the resolver two different
            # answers to "when does this end" — so the fake never produces
            # that, and M8's adapter must not either.
            return self._snapshot(
                provider_subscription_id=f"fake_{uuid.uuid4().hex[:16]}",
                status="TRIALING",
                current_period_end=trial_end,
                trial_end=trial_end,
                event="subscription.started.trial",
            )

        return self._snapshot(
            provider_subscription_id=f"fake_{uuid.uuid4().hex[:16]}",
            status="ACTIVE",
            current_period_end=now + PERIOD,
            event="subscription.started",
        )

    def renew_subscription(self, *, provider_subscription_id: str) -> ProviderSubscription:
        return self._snapshot(
            provider_subscription_id=provider_subscription_id,
            status="ACTIVE",
            current_period_end=timezone.now() + PERIOD,
            event="subscription.renewed",
        )

    def fail_payment(
        self, *, provider_subscription_id: str, current_period_end
    ) -> ProviderSubscription:
        # Echoed, not recomputed. A failed charge must not move this date:
        # extending it grants free access, and setting it to now ends access
        # immediately and makes the grace period unreachable. Whether PAST_DUE
        # still grants access is decided by the resolver from our settings,
        # never by the provider.
        return self._snapshot(
            provider_subscription_id=provider_subscription_id,
            status="PAST_DUE",
            current_period_end=current_period_end,
            event="payment.failed",
        )

    def cancel_subscription(
        self, *, provider_subscription_id: str, immediately: bool = False
    ) -> ProviderSubscription:
        now = timezone.now()

        if immediately:
            return self._snapshot(
                provider_subscription_id=provider_subscription_id,
                status="EXPIRED",
                current_period_end=now,
                event="subscription.canceled.immediate",
            )

        # The ordinary case: access continues to the end of what was paid for.
        return self._snapshot(
            provider_subscription_id=provider_subscription_id,
            status="CANCELED",
            current_period_end=now + PERIOD,
            cancel_at_period_end=True,
            event="subscription.canceled",
        )
