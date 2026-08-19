"""Base models shared across the project, and the webhook idempotency table.

The abstract bases were all this module held until M5. ADR-003 settled that
M1 creates no concrete models, because the custom ``User`` must exist before
the first migration is ever applied and it did not arrive until M2. That
ordering constraint has long since been satisfied, and ADR-012 §3 records the
decision to put ``WebhookEvent`` here rather than one copy per app.
"""

import uuid
from typing import ClassVar

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
