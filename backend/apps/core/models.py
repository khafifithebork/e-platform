"""Base models shared across the project, and the webhook idempotency table.

The abstract bases were all this module held until M5. ADR-003 settled that
M1 creates no concrete models, because the custom ``User`` must exist before
the first migration is ever applied and it did not arrive until M2. That
ordering constraint has long since been satisfied, and ADR-012 §3 records the
decision to put ``WebhookEvent`` here rather than one copy per app.
"""

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    """Records when a row was created and last changed.

    Both fields are non-editable on purpose. They describe what happened, not
    what someone would prefer had happened, and leaving them editable puts them
    into ModelForms and the admin where they can be quietly rewritten.
    """

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    """A UUID primary key, for anything whose identifier appears in a URL.

    architecture.md 5.2: sequential integers leak business information —
    ``/courses/47`` tells a competitor how many courses exist — and make
    enumeration attacks trivial.

    That section suggests UUIDv7, which is time-ordered and so keeps index
    locality. It is not available here: ``uuidv7()`` landed in PostgreSQL 18
    and the target is 16, and the standard library offers no generator, so
    adopting it would mean a third-party dependency for no benefit today.
    Revisit if the PostgreSQL version moves.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class WebhookEvent(UUIDPrimaryKeyModel, TimestampedModel):
    """Every webhook we have ever received, and the reason we can receive them twice.

    Invariant 8 fixes the handler's shape: **verify the signature, insert this
    row, enqueue a task, return 200.** No business logic in the handler, and a
    duplicate returns 200 without reprocessing.

    This table is the idempotency mechanism, not a log that happens to be
    useful. The unique constraint is what makes a retry lose: two workers can
    both ask "have I seen this event?", both see no, and both process it. Only
    a unique index makes one of them fail — and the failure it prevents is a
    subscription extended twice or a video transcoded twice, neither of which
    raises anything on its own.

    Lives in ``core`` and carries ``provider`` because it serves every
    provider that sends webhooks: the video provider in M5, the payment
    provider in M8 (ADR-012 §3). Writing the discipline once means one place
    to get the ordering right rather than two.

    ``payload`` is stored verbatim and is never read to make a decision. It is
    there so a support question weeks later has something to read, and so a
    handler bug can be replayed against the real bytes.
    """

    provider = models.CharField(max_length=32)
    provider_event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)

    # Null until the task that handles it succeeds. What separates "seen" from
    # "done": a replay arriving while the first is still in flight must still
    # be refused, so seen-ness is the insert, not this field.
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            # "What has this provider sent us lately", the first question asked
            # when a provider's events stop arriving.
            models.Index(fields=["provider", "-created_at"]),
            # Unprocessed events are the queue of things that went wrong.
            models.Index(
                fields=["provider", "created_at"],
                condition=models.Q(processed_at__isnull=True),
                name="webhook_event_unprocessed",
            ),
        ]
        constraints: ClassVar[list] = [
            # Per provider, because providers number their own events. A global
            # unique would reject one provider's event because another had
            # already used that id.
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                name="webhook_event_unique_per_provider",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_event_id}"


class AuditLogIsAppendOnly(Exception):
    """Raised by any attempt to change or remove an audit row.

    An exception rather than a silent no-op: code that thinks it is editing
    history should stop, not continue believing it succeeded.
    """


class AuditLogQuerySet(models.QuerySet):
    """Refuses the two operations that would rewrite history.

    Model-level `save` and `delete` are not enough on their own —
    `AuditLog.objects.filter(...).update(...)` and `.delete()` never touch
    them, and a bulk call is the more likely way this happens by accident.

    Django's cascade machinery is unaffected: `on_delete=SET_NULL` clears
    `actor` through `sql.UpdateQuery`, not through this class, so deleting an
    administrator still works and the row survives naming them. That is
    asserted rather than assumed — see `test_an_audit_row_outlives_its_actor`.

    A retention policy, if one ever exists, must delete through raw SQL and say
    in writing why. Making that awkward is the point.
    """

    def update(self, **kwargs):
        raise AuditLogIsAppendOnly("Audit rows are never updated.")

    def delete(self):
        raise AuditLogIsAppendOnly("Audit rows are never deleted.")


class AuditLog(UUIDPrimaryKeyModel):
    """Who did what to whom, and why. architecture.md 8.

    Every administrative action writes one of these — access overrides,
    refunds, role changes, course approvals. M10 grants a small number of
    people the ability to give away paid content and move money; the same
    capability with no trail is indistinguishable from a compromise, which is
    why this model exists before any of the capabilities that use it
    (ADR-018 1).

    **Not `TimestampedModel`**, deliberately. That base carries `updated_at`,
    and a column named "when this last changed" on an append-only table tells
    the next reader that rows change. They do not.

    Append-only means *no application path edits history* — not tamper-proof.
    A database superuser can rewrite anything, and chaining hashes without an
    external witness proves nothing a determined operator cannot reproduce.
    ADR-018 6 says so plainly rather than implying a guarantee this cannot
    make.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # SET_NULL, and the label below is what keeps the row readable
        # afterwards. PROTECT would make an audit row the reason an account
        # cannot be deleted, and that argument is eventually settled by
        # deleting audit rows — the worst outcome for the one table whose
        # only job is to be complete (ADR-018 5).
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_actions",
    )

    # Denormalised on purpose, and the one place in this codebase where that
    # is right: it is a historical fact about a moment, not a cached copy of
    # something still changing. ADR-016 3 declined denormalisation for exactly
    # the opposite reason.
    actor_label = models.CharField(
        max_length=254,
        help_text="Who acted, as it read at the time. Survives their deletion.",
    )

    action = models.CharField(max_length=64)

    target_type = models.CharField(max_length=64)
    # Text, not UUID: most targets are UUID-keyed but not all — architecture.md
    # 5.2 keeps `Language` and `Plan` on integers, and an audit log that cannot
    # record an action against them is an audit log with holes.
    target_id = models.CharField(max_length=64)

    # The reason, and anything else worth reading later. Never read to make a
    # decision — same discipline as `WebhookEvent.payload`.
    metadata = models.JSONField(default=dict, blank=True)

    # Null for actions taken from a management command, which has no request
    # and therefore no address. Recording 0.0.0.0 would be a fact we invented.
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            # architecture.md 5.4 names this exact question: "what happened to
            # this user?" It is what every access support ticket starts as.
            models.Index(
                fields=["target_type", "target_id", "-created_at"],
                name="audit_by_target_newest_first",
            ),
            # The paginator's ordering, to the letter. 6.1 lists the audit log
            # among the cursor-paginated collections, and CursorPagination
            # orders by ("-created_at", "-pk") — a composite index matching it
            # is what stops deep pages scanning the table.
            models.Index(
                fields=["-created_at", "-id"],
                name="audit_paginated_feed",
            ),
        ]
        constraints: ClassVar[list] = [
            # A row naming no actor and no target is not an audit entry. These
            # are the backstop for a caller that bypasses the service, which is
            # what invariant 11 asks for — the service checks first, and the
            # database is what makes the check unavoidable.
            models.CheckConstraint(
                condition=~models.Q(actor_label=""),
                name="audit_names_who_acted",
            ),
            models.CheckConstraint(
                condition=~models.Q(action=""),
                name="audit_names_what_happened",
            ),
            models.CheckConstraint(
                condition=~models.Q(target_type="") & ~models.Q(target_id=""),
                name="audit_names_what_it_happened_to",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.actor_label} {self.action} {self.target_type}:{self.target_id}"

    def save(self, *args, **kwargs):
        """Insert only.

        `_state.adding` rather than `self.pk is None`, because the primary key
        is a UUID generated in Python and is already set before the first
        insert — the usual check would pass for every update.
        """
        if not self._state.adding:
            raise AuditLogIsAppendOnly("Audit rows are never updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogIsAppendOnly("Audit rows are never deleted.")
