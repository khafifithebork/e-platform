"""Scheduled work for entitlements. M14 T4, and the first periodic task.

ADR-002 §4 asks for nightly entitlement reconciliation and rates it above paid
redundancy. T3 built the reconciliation; this is the half that means somebody
finds out. A report nobody runs is a report that does not exist, and the
failure it looks for — a lapsed subscription still serving paid content — is
one whose whole character is that it never announces itself.

**This task is why django-celery-beat is now a dependency.** ADR-001 §2.2
settled Beat's placement at M0 — inside the worker, at exactly one replica,
schedule in Postgres — and said explicitly that it *"lands with the first
periodic task, not in M0"*. This is that task.

**It alerts. It does not repair, and neither does the selector it reads.**
Invariant 3 has one writer of subscription state. A nightly job that quietly
corrected drift would be a second one, and it would erase the evidence of the
upstream fault that caused the drift while looking like everything was fine.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.entitlements.selectors import reconciliation_findings
from apps.notifications.emails import send_entitlement_drift_alert

logger = logging.getLogger(__name__)


@shared_task(
    # No retry. If the alert fails to enqueue, the next run is in twenty-four
    # hours and the drift will still be there — a retry storm against a broken
    # mail provider adds nothing that waiting does not.
    acks_late=True,
)
def alert_on_entitlement_drift() -> None:
    """Look for drift, and say something only if there is any.

    **Silence when clean is the point, not an optimisation.** M14 §6 case 5:
    an alert that always fires is one nobody reads, and this job runs every
    day for the life of the product. The overwhelmingly common outcome is
    nothing, and the overwhelmingly common outcome must be silent or the rare
    one is invisible.

    A log line is written either way, because "the job ran and found nothing"
    and "the job did not run" are different facts and an empty mailbox cannot
    tell them apart.

    **No deduplication, deliberately.** Drift that persists for three days
    sends three alerts. Suppressing repeats needs state about what was already
    reported, ADR-020 §8 keeps no state about email, and a subscription that is
    still giving away paid content on day three is still a live problem — a
    quieter one is not a fixed one.
    """
    findings = reconciliation_findings()

    granting = [finding for finding in findings if finding.grants_access]
    logger.info(
        "entitlement_reconciliation_ran",
        extra={
            "event": "entitlement_reconciliation_ran",
            "findings": len(findings),
            "granting_access": len(granting),
        },
    )

    if not findings:
        return

    recipient = settings.OPERATIONS_ALERT_EMAIL
    if not recipient:
        # Logged loudly rather than guessed at. An alert sent to a plausible
        # default address goes to a mailbox nobody watches, which is worse than
        # not sending: it looks like the alerting works.
        logger.warning(
            "entitlement_drift_unreported_no_recipient",
            extra={
                "event": "entitlement_drift_unreported_no_recipient",
                "findings": len(findings),
                "granting_access": len(granting),
            },
        )
        return

    send_entitlement_drift_alert(to=recipient, findings=findings)
