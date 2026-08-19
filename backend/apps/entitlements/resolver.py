"""The entitlement resolver — the most important function in this codebase.

`architecture.md` §4.5 names it that, and invariant 3 gives it three
properties that are not negotiable:

**One implementation.** Called by the API, by serializers deciding whether to
include a playback token, by the worker, by tests. If entitlement logic ever
appears in two places, they will disagree, and the one that disagrees is the
one nobody tested.

**It returns a reason, never a bare boolean.** The interface has to distinguish
"log in", "start a trial", "your payment failed" and "upgrade". A boolean forces
the frontend to re-derive state it should not know about, which is the same
logic in a second place — see above.

**Never a stored ``has_access`` column.** Derived on read. A column maintained
by a job is a two-writers problem with a payment provider, and it is wrong
whenever the job lags or an event is missed.

This module **only reads**. It is deliberately not in ``services.py``: a
resolver with a side effect answers differently the second time it is asked.

Not cached, deliberately (ADR-010 §4). §4.5 calls for a short Redis TTL
invalidated on every webhook, and there are no webhooks until M8 — a cache
whose invalidation source does not exist can only expire by timeout, so a
cancelled subscription would keep access until the TTL lapsed. The cache
arrives with the thing that invalidates it. The signature does not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Role
from apps.catalog.models import Lesson
from apps.entitlements.models import Subscription, SubscriptionStatus
from apps.entitlements.selectors import active_override_exists, subscriptions_bearing_on_access


class Reason(models.TextChoices):
    """Why access was allowed or refused.

    Stable strings: they travel to the frontend inside a Problem Details body
    and clients branch on them (ADR-004). Renaming one is an API change.
    """

    # Allowed
    PREVIEW = "PREVIEW", "Free preview lesson"
    STAFF = "STAFF", "Administrator"
    COURSE_OWNER = "COURSE_OWNER", "Instructor of this course"
    OVERRIDE = "OVERRIDE", "Manual access grant"
    SUBSCRIPTION_ACTIVE = "SUBSCRIPTION_ACTIVE", "Active subscription"
    TRIAL = "TRIAL", "Trial in progress"
    GRACE_PERIOD = "GRACE_PERIOD", "Payment failed, within grace period"
    CANCELED_BUT_PAID = "CANCELED_BUT_PAID", "Cancelled, paid period not yet over"

    # Denied
    LOGIN_REQUIRED = "LOGIN_REQUIRED", "Not signed in"
    NO_SUBSCRIPTION = "NO_SUBSCRIPTION", "Never subscribed"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED", "Subscription ended"
    TRIAL_EXPIRED = "TRIAL_EXPIRED", "Trial ended"
    TRIAL_SCOPE = "TRIAL_SCOPE", "Not included in your trial"
    GRACE_PERIOD_ENDED = "GRACE_PERIOD_ENDED", "Payment failed and grace period ended"


# What the interface should offer the person next. Kept beside the reason
# rather than derived from it in the frontend, for the same reason the reason
# exists at all.
class Cta:
    LOGIN = "login"
    SUBSCRIBE = "subscribe"
    UPDATE_PAYMENT = "update_payment"


@dataclass(frozen=True)
class AccessDecision:
    """The answer. Frozen: a decision that can be edited after the fact is a
    decision the caller can talk itself out of."""

    allowed: bool
    reason: str
    cta: str | None = None

    def __bool__(self) -> bool:
        """Truthiness follows ``allowed``, so ``if decision:`` is not a
        silently-always-true bug. Convenience only — callers that branch on a
        decision should still read ``.reason`` when reporting it."""
        return self.allowed


_ALLOW_PREVIEW = AccessDecision(True, Reason.PREVIEW)
_ALLOW_STAFF = AccessDecision(True, Reason.STAFF)
_ALLOW_OWNER = AccessDecision(True, Reason.COURSE_OWNER)
_ALLOW_OVERRIDE = AccessDecision(True, Reason.OVERRIDE)
_ALLOW_ACTIVE = AccessDecision(True, Reason.SUBSCRIPTION_ACTIVE)
_ALLOW_TRIAL = AccessDecision(True, Reason.TRIAL)
_ALLOW_GRACE = AccessDecision(True, Reason.GRACE_PERIOD)
_ALLOW_CANCELED_PAID = AccessDecision(True, Reason.CANCELED_BUT_PAID)

_DENY_LOGIN = AccessDecision(False, Reason.LOGIN_REQUIRED, Cta.LOGIN)
_DENY_NONE = AccessDecision(False, Reason.NO_SUBSCRIPTION, Cta.SUBSCRIBE)
_DENY_EXPIRED = AccessDecision(False, Reason.SUBSCRIPTION_EXPIRED, Cta.SUBSCRIBE)
_DENY_TRIAL_OVER = AccessDecision(False, Reason.TRIAL_EXPIRED, Cta.SUBSCRIBE)
_DENY_TRIAL_SCOPE = AccessDecision(False, Reason.TRIAL_SCOPE, Cta.SUBSCRIBE)
_DENY_GRACE_OVER = AccessDecision(False, Reason.GRACE_PERIOD_ENDED, Cta.UPDATE_PAYMENT)

# Denials ranked by how much they tell the person. Which one surfaces matters:
# somebody holding an expired subscription and an ended trial should be told
# their subscription ended, not that they never had one.
_DENIAL_RANK: dict[str, int] = {
    Reason.NO_SUBSCRIPTION: 0,
    Reason.TRIAL_SCOPE: 1,
    Reason.TRIAL_EXPIRED: 2,
    Reason.SUBSCRIPTION_EXPIRED: 3,
    Reason.GRACE_PERIOD_ENDED: 4,
}


def trial_covers(*, subscription: Subscription, lesson: Lesson | None) -> bool:
    """Whether this trial includes this lesson.

    **The scoping rule is undecided** (spec §3.2). It was settled that a trial
    is scoped rather than equivalent to a paid subscription, but not *what*
    scopes it — a flag on ``Course``, a relation on ``Subscription``, or a
    count of consumed lessons are three different schemas, and the last needs
    progress tracking that does not exist until M7.

    Until then this grants what an active subscription grants. That is
    permissive, and it is safe in M4 for one specific reason: **there is no
    self-serve trial**. A subscription can only be started by the ``billing``
    management command, so nobody can grant themselves a trial to exploit
    this. M9 owns the trial lifecycle and is where the narrowing belongs.

    Isolated as one function on purpose. When the rule is decided this is the
    only thing that changes, and ``test_the_trial_scope_seam_is_one_function``
    fails if the trial branch grows a second decision point somewhere else.
    """
    return True


def _decide_for(subscription: Subscription, lesson: Lesson | None, now) -> AccessDecision:
    """One subscription's answer, ignoring every other input."""
    status = subscription.status

    if status == SubscriptionStatus.ACTIVE:
        # No period check, following §4.5's flowchart. A stale ACTIVE row past
        # its period is the expiry sweep's job; denying here instead would
        # lock out a paying customer whenever a renewal event is late, which
        # is the more likely failure and the more damaging one.
        return _ALLOW_ACTIVE

    if status == SubscriptionStatus.TRIALING:
        if subscription.trial_end is not None and now >= subscription.trial_end:
            return _DENY_TRIAL_OVER
        if not trial_covers(subscription=subscription, lesson=lesson):
            return _DENY_TRIAL_SCOPE
        return _ALLOW_TRIAL

    if status == SubscriptionStatus.PAST_DUE:
        grace = timedelta(days=settings.ENTITLEMENT_GRACE_PERIOD_DAYS)
        # Measured from the end of the period that was not paid for, not from
        # the moment the charge failed: a card can fail days before the period
        # ends, and grace is meant to start when access would otherwise stop.
        if now < subscription.current_period_end + grace:
            return _ALLOW_GRACE
        return _DENY_GRACE_OVER

    if status == SubscriptionStatus.CANCELED:
        # They paid for this period. Ending access at cancellation would be
        # taking back something already bought.
        if now < subscription.current_period_end:
            return _ALLOW_CANCELED_PAID
        return _DENY_EXPIRED

    return _DENY_EXPIRED


def resolve_account_access(*, user, lesson: Lesson | None = None) -> AccessDecision:
    """Whether this account is entitled to gated content in general.

    The subscription rules, with no particular lesson in mind. ``/auth/me/``
    needs exactly this — the frontend has to know whether to show a paywall
    before any lesson is chosen — and it must not be a second implementation,
    because two copies of the entitlement rules disagree the day one of them
    changes (invariant 3). ``resolve_access`` therefore calls this rather than
    repeating it, and everything below is reached by both.

    ``lesson`` is passed through only so the trial-scope rule can see it once
    §3.2 is settled. It is ``None`` for an account-level question, which that
    rule must treat as "is anything covered", not as an error.
    """
    now = timezone.now()

    # Anonymous. Distinguished from "not entitled" because the interface must
    # offer signing in rather than subscribing.
    if user is None or not getattr(user, "is_authenticated", False):
        return _DENY_LOGIN

    if getattr(user, "role", None) == Role.ADMIN or getattr(user, "is_superuser", False):
        return _ALLOW_STAFF

    # Manual grants, before subscriptions: an override exists precisely to
    # grant access to somebody whose subscription does not.
    if active_override_exists(user=user):
        return _ALLOW_OVERRIDE

    # Subscriptions — all of them. See the selector: a user may hold a
    # cancelled row still inside its paid period alongside a fresh one.
    decisions = [
        _decide_for(subscription, lesson, now)
        for subscription in subscriptions_bearing_on_access(user=user)
    ]

    for decision in decisions:
        if decision.allowed:
            return decision

    if not decisions:
        return _DENY_NONE

    # Nothing granted access. Surface the most informative refusal rather than
    # whichever row happened to come back first.
    return max(decisions, key=lambda decision: _DENIAL_RANK[decision.reason])


def resolve_access(*, user, lesson: Lesson) -> AccessDecision:
    """Decide whether ``user`` may see ``lesson``, and say why.

    ``user`` may be ``AnonymousUser`` or ``None``: preview lessons are readable
    by people who have not signed in, so the check has to run before
    authentication is established rather than behind it.

    Only the two lesson-specific rules live here — everything about
    subscriptions is in ``resolve_account_access``, which ``/auth/me/`` calls
    too. One implementation, two entry points.

    Callers should pass a lesson with ``course`` and ``course.instructor``
    already selected. Without that the ownership check costs an extra query on
    the hottest path in the product — pinned by a query-count test (ADR-009).
    """
    # 1. Preview, before anything else. A free lesson is free to everyone, and
    #    putting this first is what keeps the marketing pages working for
    #    people with no account.
    if lesson.is_preview:
        return _ALLOW_PREVIEW

    # 2. The course's own instructor. Before the subscription rules because it
    #    needs no query — the course is already loaded — and because an
    #    instructor locked out of the course they are writing cannot check
    #    their own work.
    if (
        user is not None
        and getattr(user, "is_authenticated", False)
        and lesson.course.instructor_id == user.pk
    ):
        return _ALLOW_OWNER

    return resolve_account_access(user=user, lesson=lesson)
