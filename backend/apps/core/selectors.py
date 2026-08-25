"""Reads over the audit log.

`audit.py` is the one writer; this is the one reader, and for the same reason.
An audit trail assembled by six callers with slightly different ideas of what
"everything that happened to this user" means is a trail that answers a support
question differently depending on which screen asked it.

Kept in `core` beside the model rather than in the app that wants the answer,
so no product app imports `AuditLog` directly. That is the shape M6 used for
`Transcript`, and the reason is the same: a second reader is invisible to
behavioural tests and shows up as a disagreement in production.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.core.models import AuditLog


def admin_actions_against(*, target, limit: int | None = None) -> QuerySet[AuditLog]:
    """What administrators did to one object, newest first.

    Matched on `(target_type, target_id)` — the pair the writer records and the
    pair `audit_by_target_newest_first` indexes. architecture.md §5.4 names
    this exact query as the one every access support ticket begins as.

    **No join, and no test can prove that.** `actor_label` was denormalised so
    this read needs none. Adding `select_related("actor")` was tried: every
    test still passes, because a join changes the shape of one query rather
    than the number of them. So the reason to leave it off is not performance
    — it is that the join buys a column the row already carries, and carries
    *nothing* for rows whose actor has since been deleted, which is the case
    the denormalisation exists for. ADR-009, in its usual disguise: the
    plausible performance sentence was the wrong one.
    """
    rows = AuditLog.objects.filter(
        target_type=target._meta.model_name,
        target_id=str(target.pk),
    )
    return rows[:limit] if limit is not None else rows
