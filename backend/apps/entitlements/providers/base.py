"""The billing provider interface.

Invariant 4: every external provider sits behind an adapter, and vendor SDKs
are imported nowhere else. architecture.md §10 makes the sharper point for
media, and it holds identically here — write the interface before the vendor
code, because the interface is the thing that keeps the provider replaceable.

**An adapter never touches the ORM.** It takes and returns plain data; the
service layer decides what that means for our database. That is the seam M8
depends on: a real provider replaces `FakeBillingProvider` and
``services.py`` does not change. If an adapter ever imports a model, the
provider has stopped being replaceable and entitlement logic has started
leaking into vendor code — which is the failure CLAUDE.md §10 describes as
"writing access rules inside a webhook handler".

The vocabulary here is **ours**, not any provider's. Nothing in this module
describes a real payment API, because the payment provider is undecided
(CLAUDE.md §11 #1) and inventing its capabilities is forbidden by §6. M8's
adapter translates whatever the chosen provider actually sends into these
shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderSubscription:
    """A normalised snapshot of what the provider believes is true.

    Frozen, because it is a report rather than a working object. Anything that
    wants to change subscription state goes through ``services.py``, which is
    the only writer.

    Deliberately carries no money. There is no amount, currency, interval or
    price id here: entitlement needs to know *when access ends*, and nothing
    about what was charged. Those fields arrive with the payment provider in
    M8, in a model this one feeds rather than becomes.
    """

    provider: str
    provider_subscription_id: str
    status: str
    current_period_end: datetime
    trial_end: datetime | None = None
    cancel_at_period_end: bool = False
    # Whatever the provider actually sent, kept verbatim so a support question
    # six weeks later has something to read. Never parsed to make a decision.
    raw: dict = field(default_factory=dict)


@runtime_checkable
class BillingProvider(Protocol):
    """What any billing provider must be able to do for us.

    Small on purpose. Each method exists because M4 exercises it; there is no
    speculative surface for capabilities no provider has been chosen to have.
    """

    name: str

    def start_subscription(
        self, *, reference: str, trial_days: int | None = None
    ) -> ProviderSubscription:
        """Begin a subscription, optionally as a trial.

        ``reference`` is our opaque handle for the subscriber — an id we
        already have, never an email address, so that an adapter cannot become
        a route by which personal data reaches a third party.
        """
        ...

    def renew_subscription(self, *, provider_subscription_id: str) -> ProviderSubscription:
        """A period elapsed and was paid for."""
        ...

    def fail_payment(
        self, *, provider_subscription_id: str, current_period_end: datetime
    ) -> ProviderSubscription:
        """A charge failed. Whether that ends access is our decision, not the
        provider's — see the grace period in ``resolve_access``.

        Takes the period end rather than inventing one. A failed charge must
        not move that date: extending it would grant free access, and setting
        it to now would end access immediately and make the grace period
        unreachable. A real provider already knows the value and sends it; the
        fake holds no state, so the caller supplies what it has.
        """
        ...

    def cancel_subscription(
        self, *, provider_subscription_id: str, immediately: bool = False
    ) -> ProviderSubscription:
        """Stop renewing. ``immediately`` ends access now rather than at the
        end of the paid period."""
        ...
