"""Subscription writes — the only place subscription state changes.

The shape M3 proved with the course state machine, for the same reason: once a
status assignment appears in a management command, a webhook handler and an
admin action, the three drift, and the one that drifts is the one nobody
tested. CLAUDE.md §10 names this exact failure for M4 — "if you find yourself
writing access rules inside a webhook handler, you have gone wrong".

The provider is asked what it believes; this module decides what that means
for our database and records why. The adapter never writes a row and this
module never imports a vendor SDK.

Reading access is not here. ``resolve_access`` is a *read*, lives in its own
module, and never writes — a resolver with a side effect is a resolver that
behaves differently the second time it is asked.
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar, NoReturn

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.audit import AdminAction, record_admin_action
from apps.entitlements.models import (
    LIVE_STATUSES,
    AccessOverride,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)
from apps.entitlements.providers.base import BillingProvider, ProviderSubscription


class SubscriptionTransitionError(Exception):
    """The subscription is not in a state this transition can leave."""


class NoLiveSubscription(Exception):
    """This user has nothing to act on."""


# Every legal move, in one table. Absent means impossible, whoever asks.
#
# There is no ACTIVE -> TRIALING entry: a trial is how a subscription begins,
# and letting a paying subscription revert to trialing would be free access
# granted by a state change nobody would think to test.
ALLOWED_TRANSITIONS: ClassVar[set[tuple[str, str]]] = {
    (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE),
    (SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE),
    (SubscriptionStatus.TRIALING, SubscriptionStatus.CANCELED),
    (SubscriptionStatus.TRIALING, SubscriptionStatus.EXPIRED),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE),  # renewal
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED),
    # Recovery: a retried card succeeds.
    (SubscriptionStatus.PAST_DUE, SubscriptionStatus.ACTIVE),
    (SubscriptionStatus.PAST_DUE, SubscriptionStatus.CANCELED),
    (SubscriptionStatus.PAST_DUE, SubscriptionStatus.EXPIRED),
    # A cancelled subscription runs out its paid period, then expires.
    (SubscriptionStatus.CANCELED, SubscriptionStatus.EXPIRED),
}

_EVENT_FOR: ClassVar[dict[str, str]] = {
    SubscriptionStatus.ACTIVE: SubscriptionEvent.EventType.ACTIVATED,
    SubscriptionStatus.PAST_DUE: SubscriptionEvent.EventType.PAYMENT_FAILED,
    SubscriptionStatus.CANCELED: SubscriptionEvent.EventType.CANCELED,
    SubscriptionStatus.EXPIRED: SubscriptionEvent.EventType.EXPIRED,
}


def live_subscription(*, user: User) -> Subscription:
    """The user's current subscription, or raise.

    ``LIVE_STATUSES`` excludes CANCELED deliberately (see the model): a
    cancelled subscription still grants access to the end of its period, but it
    is not the row a new transition acts on.
    """
    subscription = Subscription.objects.filter(user=user, status__in=LIVE_STATUSES).first()
    if subscription is None:
        raise NoLiveSubscription
    return subscription


def _apply(
    *,
    subscription: Subscription,
    snapshot: ProviderSubscription,
    event_type: str | None = None,
) -> Subscription:
    """Write the provider's snapshot onto our row, with a reason beside it."""
    previous = subscription.status

    if (previous, snapshot.status) not in ALLOWED_TRANSITIONS:
        raise SubscriptionTransitionError(f"{previous} -> {snapshot.status}")

    subscription.status = snapshot.status
    subscription.current_period_end = snapshot.current_period_end
    subscription.cancel_at_period_end = snapshot.cancel_at_period_end
    if snapshot.trial_end is not None:
        # Never cleared. "When did their trial end" is a question support asks,
        # and a nulled column cannot answer it.
        subscription.trial_end = snapshot.trial_end
    subscription.save(
        update_fields=[
            "status",
            "current_period_end",
            "cancel_at_period_end",
            "trial_end",
            "updated_at",
        ]
    )

    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type=event_type or _EVENT_FOR[snapshot.status],
        from_status=previous,
        to_status=snapshot.status,
        provider_payload=snapshot.raw,
    )
    return subscription


@transaction.atomic
def start_subscription(
    *, user: User, provider: BillingProvider, trial_days: int | None = None
) -> Subscription:
    """Begin a subscription for a user who has none live.

    The uniqueness of a live subscription is enforced by a database constraint,
    not by this check — two concurrent calls would both pass the check and one
    must still lose. This exists to turn that collision into a clear error
    rather than an IntegrityError surfacing from four frames down.
    """
    if Subscription.objects.filter(user=user, status__in=LIVE_STATUSES).exists():
        raise SubscriptionTransitionError("This user already has a live subscription.")

    snapshot = provider.start_subscription(reference=str(user.pk), trial_days=trial_days)

    subscription = Subscription.objects.create(
        user=user,
        status=snapshot.status,
        current_period_end=snapshot.current_period_end,
        trial_end=snapshot.trial_end,
        cancel_at_period_end=snapshot.cancel_at_period_end,
        provider=snapshot.provider,
        provider_subscription_id=snapshot.provider_subscription_id,
    )
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type=(
            SubscriptionEvent.EventType.TRIAL_STARTED
            if trial_days is not None
            else SubscriptionEvent.EventType.ACTIVATED
        ),
        to_status=snapshot.status,
        provider_payload=snapshot.raw,
    )
    return subscription


@transaction.atomic
def renew(*, subscription: Subscription, provider: BillingProvider) -> Subscription:
    """A period elapsed and was paid for."""
    snapshot = provider.renew_subscription(
        provider_subscription_id=subscription.provider_subscription_id
    )
    return _apply(
        subscription=subscription,
        snapshot=snapshot,
        event_type=SubscriptionEvent.EventType.RENEWED,
    )


@transaction.atomic
def fail_payment(*, subscription: Subscription, provider: BillingProvider) -> Subscription:
    """A charge failed. Access is not decided here — the resolver applies the
    grace period, and this only records that the charge did not go through."""
    snapshot = provider.fail_payment(
        provider_subscription_id=subscription.provider_subscription_id,
        current_period_end=subscription.current_period_end,
    )
    return _apply(subscription=subscription, snapshot=snapshot)


@transaction.atomic
def cancel(
    *, subscription: Subscription, provider: BillingProvider, immediately: bool = False
) -> Subscription:
    """Stop renewing.

    The ordinary path keeps access to the end of the paid period, because the
    customer paid for it. ``immediately`` is the support path — a refund, or an
    account being closed — and ends access now.
    """
    snapshot = provider.cancel_subscription(
        provider_subscription_id=subscription.provider_subscription_id,
        immediately=immediately,
    )
    return _apply(
        subscription=subscription,
        snapshot=snapshot,
        event_type=(
            SubscriptionEvent.EventType.EXPIRED
            if immediately
            else SubscriptionEvent.EventType.CANCELLATION_REQUESTED
        ),
    )


@transaction.atomic
def expire(*, subscription: Subscription) -> Subscription:
    """The period ended and nothing renewed it.

    No provider call: this is a consequence of time passing, which we observe
    ourselves. M9's expiry sweep is the caller that matters; the management
    command exists so the state is reachable in development.
    """
    previous = subscription.status
    if (previous, SubscriptionStatus.EXPIRED) not in ALLOWED_TRANSITIONS:
        raise SubscriptionTransitionError(f"{previous} -> EXPIRED")

    subscription.status = SubscriptionStatus.EXPIRED
    subscription.save(update_fields=["status", "updated_at"])

    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type=SubscriptionEvent.EventType.EXPIRED,
        from_status=previous,
        to_status=SubscriptionStatus.EXPIRED,
    )
    return subscription


class InvalidOverride(Exception):
    """A grant that would not be time-bounded, or would not say why.

    Both are the boolean §5.2 rejects, arriving in a shape that looks like the
    table that replaced it.
    """


def grant_access_override(
    *,
    actor: User,
    user: User,
    days: int,
    reason: str,
    request=None,
) -> AccessOverride:
    """Give one person access the billing system does not.

    **Days, not an end date.** A support person thinks "give them two weeks",
    and taking a duration makes two failures impossible by construction: an
    override that expired before it was created, and one with no end at all.
    §5.2 rejects manual access as a boolean precisely because it never ends.

    Audited in the same transaction as the grant. If the write fails the row
    describing it goes too, and if the audit fails the grant does — which is
    the correct pairing for a capability that hands out paid content.

    Self-grants are allowed and recorded like any other. Blocking them would
    be theatre: an administrator who wants free access can grant it to a second
    account they control. The control that works is the one that makes it
    visible (spec §4, case 10).
    """
    if days < 1 or days > settings.ACCESS_OVERRIDE_MAX_DAYS:
        raise InvalidOverride(
            f"An override runs between 1 and {settings.ACCESS_OVERRIDE_MAX_DAYS} days."
        )

    if not reason or not reason.strip():
        # Checked here as well as in the database, because the service is
        # reachable from a management command where no serializer runs.
        raise InvalidOverride("An override must record why it was granted.")

    now = timezone.now()

    with transaction.atomic():
        override = AccessOverride.objects.create(
            user=user,
            granted_by=actor,
            reason=reason.strip(),
            starts_at=now,
            ends_at=now + timedelta(days=days),
        )
        record_admin_action(
            actor=actor,
            action=AdminAction.ACCESS_OVERRIDE_GRANTED,
            target=user,
            reason=reason,
            request=request,
            days=days,
            ends_at=override.ends_at.isoformat(),
            override_id=str(override.pk),
        )

    return override


class InvalidRefund(Exception):
    """A refund request that could not be recorded even if it could be made."""


class RefundNotAvailable(Exception):
    """There is no payment provider to refund from. Deliberately fatal.

    §11 #1 leaves the payment provider and jurisdiction undecided, so there is
    nothing to call and no honest way to fake one: refund semantics are the
    provider's, not ours — whether partial refunds exist, whether there is a
    window, whether an idempotency key is mandatory, whether the result is
    synchronous or arrives later by webhook. ADR-018 §3 declined to invent
    answers to those, because a test against an invented answer is confidence
    in behaviour nobody has verified.

    This reads as unfinished because it is. That is the point (spec §2.2).
    """


def issue_refund(
    *,
    actor: User | None,
    subscription: Subscription,
    reason: str,
    request=None,
) -> NoReturn:
    """Refund a subscription. Raises, always, until M8 supplies an adapter.

    **What this builds and why now.** The permission boundary, the validation
    and the audit obligation are ours and are the parts that must not be bolted
    on hastily beside a live payments integration (ADR-018 §3). Everything
    checked above the refusal below is inherited by M8; anything left unchecked
    is something M8 has to write while holding a provider's SDK in its other
    hand.

    **No audit row is written**, and that is a decision rather than an
    omission. A refund that raised did not happen, and a row describing an
    action that did not happen is a false record — the same line the suite
    already holds for a refused course approval. ``REFUND_ISSUED`` stays in
    ``AdminAction`` as the marker; M8 is what makes it reachable.

    **No subscription state changes either.** Revoking access here would be a
    half-done refund: the learner loses the content and keeps the charge. If
    access should end when money is returned, that is one decision made in one
    place once a provider exists, not two halves shipped a milestone apart.

    ``subscription`` and ``request`` are accepted and not read, which is worth
    saying plainly rather than leaving to be discovered: there is nothing yet
    to refund them against and nothing yet to record an address on. They are in
    the signature because M8 should be adding a provider call to a finished
    service rather than a signature to a stub. ``actor`` *is* read — the check
    below is real.
    """
    if actor is None or not getattr(actor, "pk", None):
        # The rule `record_admin_action` will apply in M8, applied now so the
        # refund service does not meet it for the first time next to a live
        # provider.
        raise InvalidRefund("A refund must name who issued it.")

    if not reason or not reason.strip():
        # Checked here as well as in the serializer: this is reachable from a
        # management command, where no serializer runs.
        raise InvalidRefund("A refund must record why it was issued.")

    raise RefundNotAvailable(
        "Refunds require a payment provider, which M8 integrates. "
        "The subscription was not changed and nothing was recorded."
    )
