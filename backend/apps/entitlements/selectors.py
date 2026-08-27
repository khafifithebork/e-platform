"""Entitlement reads.

Separate from ``services.py`` because a resolver must never write. A read with
a side effect answers differently the second time it is asked, which in this
part of the system means access that depends on how often it was checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.core.selectors import admin_actions_against
from apps.entitlements.models import (
    LIVE_STATUSES,
    AccessOverride,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)


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


@dataclass(frozen=True)
class Finding:
    """One category of drift, and how much of it there is.

    Carries a count and a handful of example ids rather than every row. An
    alert that embeds ten thousand subscription ids is an alert nobody opens,
    and the ids are only there so somebody can go and look at one.

    `grants_access` is the field that matters. Two of these categories are
    housekeeping — rows the resolver already refuses — and one is a subscription
    still handing out paid content. Reporting them as a single number would
    bury the only one worth waking up for.
    """

    code: str
    description: str
    grants_access: bool
    count: int
    examples: tuple[str, ...]


# How many ids to carry. Enough to investigate, few enough to read.
FINDING_EXAMPLES = 5


def reconciliation_findings(*, now=None) -> list[Finding]:
    """Where stored subscription state has drifted from what it should be.

    **Reports; never repairs.** Invariant 3 has exactly one place that decides
    access and one that writes subscription state. A job that quietly corrected
    rows here would be a second writer, and the failure mode is the worst
    available: it would look like nothing was ever wrong.

    **Read-only, and the tests prove it** rather than the docstring asserting
    it.

    The categories are deliberately split by whether they *grant access*:

    - `ACTIVE_PAST_PERIOD` is the one that costs money. `resolver._decide_for`
      allows an ACTIVE subscription without checking the period, on the
      explicit grounds that "a stale ACTIVE row past its period is the expiry
      sweep's job" — and denying there instead would lock out a paying customer
      whenever a renewal event is late. That reasoning is right, and it assumes
      a sweep exists. **None does.** Until M8 writes one, this is how anyone
      finds out.
    - The rest are rows the resolver already refuses. They are worth reporting
      because they mean something upstream stopped happening, and worth
      separating because none of them is giving anything away.
    """
    now = now or timezone.now()
    grace = timedelta(days=settings.ENTITLEMENT_GRACE_PERIOD_DAYS)

    categories = [
        (
            "ACTIVE_PAST_PERIOD",
            "ACTIVE past its paid period — still granting access, with no renewal",
            True,
            Q(status=SubscriptionStatus.ACTIVE, current_period_end__lt=now),
        ),
        (
            "TRIALING_PAST_END",
            "TRIALING past trial_end — access already refused, row stale",
            False,
            Q(status=SubscriptionStatus.TRIALING, trial_end__lt=now),
        ),
        (
            "PAST_DUE_BEYOND_GRACE",
            "PAST_DUE beyond the grace period — access already refused, row stale",
            False,
            Q(status=SubscriptionStatus.PAST_DUE, current_period_end__lt=now - grace),
        ),
        (
            "CANCELED_PAST_PERIOD",
            "CANCELED past its paid period — access already refused, row stale",
            False,
            Q(status=SubscriptionStatus.CANCELED, current_period_end__lt=now),
        ),
    ]

    findings: list[Finding] = []
    for code, description, grants_access, condition in categories:
        # One count and one slice per category — four pairs of queries however
        # many subscriptions exist. Iterating rows to classify them in Python
        # is the shape that works until it is the thing that times out at 3am.
        matching = Subscription.objects.filter(condition)
        count = matching.count()
        if not count:
            continue
        examples = tuple(
            str(pk)
            for pk in matching.order_by("pk").values_list("pk", flat=True)[:FINDING_EXAMPLES]
        )
        findings.append(
            Finding(
                code=code,
                description=description,
                grants_access=grants_access,
                count=count,
                examples=examples,
            )
        )

    # The database constraint should make this impossible. It is checked anyway,
    # because "impossible" is a property of the constraint still being there —
    # and a dropped constraint is exactly the kind of thing that is discovered
    # by its consequences rather than by its absence.
    duplicated = (
        Subscription.objects.filter(status__in=LIVE_STATUSES)
        .values("user_id")
        .annotate(live=Count("id"))
        .filter(live__gt=1)
    )
    duplicates = list(duplicated[:FINDING_EXAMPLES])
    if duplicates:
        findings.append(
            Finding(
                code="MULTIPLE_LIVE_SUBSCRIPTIONS",
                description=(
                    "More than one live subscription for one user — "
                    "the unique constraint is not holding"
                ),
                grants_access=True,
                count=duplicated.count(),
                examples=tuple(str(row["user_id"]) for row in duplicates),
            )
        )

    return findings
