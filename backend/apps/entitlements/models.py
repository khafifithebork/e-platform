"""Subscription state and manual grants — the inputs to the resolver.

These models hold **our** state, not a payment provider's. The provider is two
opaque strings (`provider`, `provider_subscription_id`), which is invariant 7's
pattern applied to billing: store who told us and their id for it, never their
object model. architecture.md §5 says the same thing from the other direction —
"PostgreSQL is the single source of truth, including for entitlement. Payment
providers are an *event feed into* your database, never a thing you query at
request time."

Nothing here carries a price, an interval, a currency or an invoice. The
payment provider is undecided (CLAUDE.md §11 #1) and the standing rule is that
billing is not modelled; ADR-010 §1 records why `Plan` waits for M8.

Every invariant below is a database constraint, not a validator (invariant 11).
Two concurrent requests can both check "does this user already have a live
subscription?", both see no, and both insert — only a unique index makes one of
them lose.
"""

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel, UUIDPrimaryKeyModel


class SubscriptionStatus(models.TextChoices):
    """The states a subscription can be in.

    Names chosen to match what payment providers broadly agree on, so that M8's
    adapter maps rather than translates. The *meaning* is ours: what each state
    grants is decided by the resolver, never by the provider.
    """

    TRIALING = "TRIALING", "Trialing"
    ACTIVE = "ACTIVE", "Active"
    PAST_DUE = "PAST_DUE", "Past due"
    CANCELED = "CANCELED", "Canceled"
    EXPIRED = "EXPIRED", "Expired"


# The statuses that mean "this subscription is the user's current one".
#
# CANCELED is deliberately absent. A cancelled subscription still grants access
# until its period ends, so its row must survive alongside a fresh one when
# someone resubscribes before expiry. That is also why the resolver must
# consider *all* of a user's subscriptions rather than fetching one and
# assuming it is the only one — see ADR-010 and the T4 resolver.
LIVE_STATUSES: tuple[str, ...] = (
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
)


class Subscription(UUIDPrimaryKeyModel, TimestampedModel):
    """One user's subscription, in one state, with the dates that bound it."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # PROTECT (§5.4): deleting a user must not silently erase the record of
        # what they were entitled to and paid for. Deactivation is a real flow,
        # and GDPR erasure anonymises the person while keeping the history.
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    status = models.CharField(max_length=16, choices=SubscriptionStatus.choices)

    # When the current paid or trial period ends. Non-null: a subscription with
    # no end is one the resolver has no boundary to compare against, and
    # "access until further notice" is not a state this product has.
    current_period_end = models.DateTimeField()

    # Null except while TRIALING, where a constraint requires it. Kept after the
    # trial converts, because "when did their trial end" is a question support
    # asks and a nulled column cannot answer.
    trial_end = models.DateTimeField(null=True, blank=True)

    cancel_at_period_end = models.BooleanField(
        default=False,
        help_text="Cancellation requested; access continues until current_period_end.",
    )

    provider = models.CharField(
        max_length=32,
        help_text="Which system told us about this. 'fake' until M8.",
    )
    # NULL rather than "" against ruff's DJ001, and the exception is the whole
    # point: PostgreSQL treats NULLs as distinct, so any number of rows may
    # have no provider id. With "" every unbilled row would be ("fake", "")
    # and the unique constraint below would refuse the second subscription in
    # the system. `test_many_rows_may_have_no_provider_id` pins that.
    provider_subscription_id = models.CharField(  # noqa: DJ001
        max_length=128,
        null=True,
        blank=True,
        help_text="The provider's opaque id. Null until a real provider exists.",
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            # §5.3: entitlement checks and expiry sweeps only care about live
            # rows, and a partial index over them stays small as cancelled and
            # expired subscriptions accumulate for the lifetime of the product.
            models.Index(
                fields=["user"],
                condition=models.Q(status__in=LIVE_STATUSES),
                name="subscription_live_by_user",
            ),
            # Renewal and expiry sweeps.
            models.Index(fields=["status", "current_period_end"]),
        ]
        constraints: ClassVar[list] = [
            # At most one live subscription per user. Double access, and later
            # double billing, is what this prevents — and it has to be an index
            # because the check-then-insert race cannot be closed in Python.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status__in=LIVE_STATUSES),
                name="one_live_subscription_per_user",
            ),
            # A trial with no end never expires: the resolver would read
            # trial_end as None and have no boundary to compare against. Better
            # impossible than handled.
            models.CheckConstraint(
                condition=~models.Q(status=SubscriptionStatus.TRIALING)
                | models.Q(trial_end__isnull=False),
                name="trialing_requires_a_trial_end",
            ),
            # §5.3. M8 looks a subscription up by the provider's id when a
            # webhook arrives; two rows sharing one would make that lookup
            # ambiguous at exactly the moment money is involved. Nulls do not
            # collide in PostgreSQL, so unbilled rows are unaffected.
            models.UniqueConstraint(
                fields=["provider", "provider_subscription_id"],
                name="subscription_unique_per_provider_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.status} subscription for {self.user_id}"


class SubscriptionEvent(UUIDPrimaryKeyModel, TimestampedModel):
    """Append-only record of everything that happened to a subscription.

    §5.2: a mutable ``status`` answers *what is true now*; it cannot answer
    *why is this person's access wrong*, which is the actual support ticket.
    M3 proved the same shape with ``CourseReviewEvent``.

    ``from_status``/``to_status`` are plain text rather than choices on purpose.
    This is a log: it must be able to record a transition whose vocabulary has
    since changed, and a historic row failing validation because an enum member
    was renamed would destroy the thing the log exists for.
    """

    class EventType(models.TextChoices):
        TRIAL_STARTED = "TRIAL_STARTED", "Trial started"
        ACTIVATED = "ACTIVATED", "Activated"
        RENEWED = "RENEWED", "Renewed"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment failed"
        CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED", "Cancellation requested"
        CANCELED = "CANCELED", "Canceled"
        EXPIRED = "EXPIRED", "Expired"

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16, blank=True)

    # Whatever the provider sent, kept verbatim for diagnosis. Never read to
    # make a decision — that is what the columns above are for.
    provider_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            models.Index(fields=["subscription", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} on {self.subscription_id}"


class AccessOverride(UUIDPrimaryKeyModel, TimestampedModel):
    """A manual, time-bounded grant of access.

    §5.2 is explicit that this is a table and not a boolean on ``User``: as a
    flag it is permanent, unexplained, and nobody dares remove it. As a row it
    expires by itself, says who granted it and why, and composes into the
    resolver as one more branch.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="access_overrides",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # PROTECT (§5.4), same reason as everywhere else an actor is recorded:
        # an override whose grantor vanished is an unexplained grant, which is
        # exactly what this table exists to prevent.
        on_delete=models.PROTECT,
        related_name="access_overrides_granted",
    )
    reason = models.TextField(
        help_text="Why this was granted. Required — an unexplained grant is the boolean again."
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering: ClassVar[list[str]] = ["-starts_at"]
        indexes: ClassVar[list] = [
            # The resolver's question: does this user hold an override covering
            # now? Filtered by user, bounded by both dates.
            models.Index(fields=["user", "starts_at", "ends_at"]),
        ]
        constraints: ClassVar[list] = [
            # Zero or negative duration grants nothing and is far more likely a
            # bug than an intention.
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="override_ends_after_it_starts",
            ),
            # The reason is the point of the table. Enforced in the database
            # because a blank one turns this back into the flag §5.2 rejects.
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="override_requires_a_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"Override for {self.user_id} until {self.ends_at}"
