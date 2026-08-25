"""Entitlement reads.

Separate from ``services.py`` because a resolver must never write. A read with
a side effect answers differently the second time it is asked, which in this
part of the system means access that depends on how often it was checked.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.core.selectors import admin_actions_against
from apps.entitlements.models import AccessOverride, Subscription, SubscriptionEvent


def subscriptions_bearing_on_access(*, user: User):
    """Every subscription that could grant this user access.

    All of them, not one. A user may legitimately hold a CANCELED row still
    inside its paid period *and* a fresh ACTIVE one — the live-subscription
    constraint excludes CANCELED precisely so resubscribing before expiry is
    possible. Fetching "the" subscription and reasoning about it would answer
    correctly for most users and deny access to the ones who resubscribed
    early, which is a support ticket from someone who has just paid.

    EXPIRED rows are included so the resolver can distinguish "your
    subscription ran out" from "you never had one" — different messages, and
    the difference is the whole reason decisions carry a reason.
    """
    return Subscription.objects.filter(user=user).only("status", "current_period_end", "trial_end")


def active_override_exists(*, user: User) -> bool:
    """Whether a manual grant covers this moment.

    Bounded at both ends in the query rather than in Python: an override that
    has not started yet and one that finished yesterday are both inactive, and
    filtering on only one bound is the kind of mistake that grants a year of
    free access to whoever was given a week of it.
    """
    now = timezone.now()
    return AccessOverride.objects.filter(
        Q(user=user) & Q(starts_at__lte=now) & Q(ends_at__gt=now)
    ).exists()


def diagnostics_for(*, user: User):
    """Everything bearing on one person's entitlement, for support.

    Three queries returned together rather than a view assembling them, so
    that "what do we show when access is wrong" is answered in one place and
    the ordering is deliberate: subscriptions and events newest first, because
    a support question is almost always about what happened most recently.

    Overrides are joined on their grantor: the whole argument for a table over
    a boolean (§5.2) is that a grant says who made it, and rendering that
    without the join is one query per row.
    """
    return (
        Subscription.objects.filter(user=user).order_by("-created_at"),
        SubscriptionEvent.objects.filter(subscription__user=user)
        .select_related("subscription")
        .order_by("-created_at"),
        AccessOverride.objects.filter(user=user)
        .select_related("granted_by")
        .order_by("-starts_at"),
    )


# Diagnostics renders inline with no pagination, and audit rows accumulate for
# the life of an account. Fifty is enough to answer "what did we do to this
# person recently", which is the question §5.4 says support arrives with; the
# whole history is readable in the admin site, which is paginated and can be
# searched. The total is returned beside the rows so a truncated list is
# visibly truncated rather than quietly short.
DIAGNOSTIC_TRAIL_LIMIT = 50


def admin_trail_for(*, user: User) -> tuple[list, int]:
    """What administrators have done to this account, and how much there is.

    **User-targeted rows only.** An override and a role change record the user
    as their target; a course approval records the course, and a refund will
    record the subscription. So an instructor's approvals do not appear here
    and neither will a refund — settled 2026-08-25 rather than joining through
    every object a user owns, because T8 makes a refund impossible today and
    the join would be a path no test could reach. **M8 must revisit this**, or
    the first refund will be absent from the screen support opens to ask about
    it.

    Two queries, not one: the page needs the count as well as the rows, and a
    `LIMIT` cannot report what it cut off.
    """
    rows = admin_actions_against(target=user, limit=DIAGNOSTIC_TRAIL_LIMIT)
    total = admin_actions_against(target=user).count()
    return list(rows), total
