"""Recording administrative actions. architecture.md §8.

**One writer.** Every audit row in the system is created here, and a structural
test asserts nothing else calls `AuditLog.objects.create`. That is what makes
the vocabulary closed and the shape consistent — an audit trail assembled by
six callers with slightly different ideas of what `target_id` means is a table
you cannot query.

Called from the service that performs the action, inside the same transaction.
Not from the view: a view that audits is a view containing business knowledge
(invariant 2), and worse, it audits what it *asked for* rather than what
happened. If the write rolls back, the row describing it must go too — there is
a test for that.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import AuditLog


class AdminAction(models.TextChoices):
    """The closed vocabulary.

    §8 names the four that must be audited — *override, refund, role change,
    course approval* — so this list mirrors the document rather than inventing
    a taxonomy. Each value arrives with the task that performs it.

    Closed rather than free text because a typo produces a row that is real,
    permanent and unfindable: nobody searching `ACCESS_OVERRIDE_GRANTED` will
    ever see `ACCESS_OVERRIDE_GRANT`, and the audit log's whole value is that
    a search for what happened returns everything that happened.
    """

    ACCESS_OVERRIDE_GRANTED = "ACCESS_OVERRIDE_GRANTED", "Access override granted"
    ACCESS_OVERRIDE_REVOKED = "ACCESS_OVERRIDE_REVOKED", "Access override revoked"
    COURSE_APPROVED = "COURSE_APPROVED", "Course approved"
    COURSE_REJECTED = "COURSE_REJECTED", "Course rejected"
    COURSE_CHANGES_REQUESTED = "COURSE_CHANGES_REQUESTED", "Course changes requested"
    ROLE_CHANGED = "ROLE_CHANGED", "Role changed"
    REFUND_ISSUED = "REFUND_ISSUED", "Refund issued"


class NotAuditable(Exception):
    """Raised when an action cannot be recorded completely.

    Deliberately fatal. The alternative — write the row with the missing piece
    blank — produces an audit trail that answers "somebody did something to
    someone", which is worse than none because it looks like coverage.
    """


def client_ip(request) -> str | None:
    """The address the request came from, as far as we can honestly tell.

    `REMOTE_ADDR`, and **not** `X-Forwarded-For`. That header is set by the
    client and is only trustworthy after stripping a known number of trusted
    proxies; parsing it without that is recording an attacker-supplied string
    as fact.

    The consequence, observed rather than assumed: behind the Next.js rewrite
    Django sees the proxy's address — `172.19.0.7` in the compose stack — not
    the administrator's. So this column currently answers "which of our
    machines relayed it", which is nearly worthless, and it is recorded anyway
    because a null would be indistinguishable from a management command.

    `django-axes` has exactly the same limitation today and for the same
    reason, so its per-IP lockout and this column at least agree with each
    other. Fixing both means knowing the trusted proxy depth, which is a
    deployment fact — **M13**.
    """
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record_admin_action(
    *,
    actor,
    action: str,
    target,
    reason: str,
    request=None,
    **details,
) -> AuditLog:
    """Write one audit row. §8: actor, target, reason, IP.

    `target` is a model instance rather than a type/id pair, so the two can
    never disagree and a caller cannot record an action against a target that
    does not exist.

    `reason` is required and must say something. §5 is explicit that an
    override modelled without one becomes "a permanent unexplained flag that
    nobody dares remove", and the same is true of every action here: the row
    exists to answer *why*, six weeks later, to somebody who was not there.

    Extra `details` land in `metadata` beside the reason — the days granted,
    the amount refunded, the role moved from and to. Never read to make a
    decision, same discipline as `WebhookEvent.payload`.
    """
    if actor is None or not getattr(actor, "pk", None):
        raise NotAuditable("An administrative action must name who took it.")

    label = getattr(actor, "email", "") or ""
    if not label:
        raise NotAuditable("The actor has no label to record.")

    if action not in AdminAction.values:
        # A typo here is a permanent, unfindable row. Refusing costs one
        # exception in development; allowing it costs a gap in the trail that
        # nobody discovers until they go looking for something that is not
        # there.
        raise NotAuditable(f"{action!r} is not a known administrative action.")

    if not reason or not reason.strip():
        raise NotAuditable("An administrative action must record why.")

    if target is None or getattr(target, "pk", None) is None:
        raise NotAuditable("An administrative action must name what it acted on.")

    return AuditLog.objects.create(
        actor=actor,
        actor_label=label,
        action=action,
        target_type=target._meta.model_name,
        target_id=str(target.pk),
        metadata={"reason": reason.strip(), **details},
        ip_address=client_ip(request),
    )
