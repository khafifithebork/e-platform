"""Delivering email, off the request path.

**Why this exists at all.** Both of M2's callers ran `send_mail` inside the
view that handled the request, so a learner's registration latency was a
function of an SMTP handshake, and a mail server having a slow minute became a
slow minute for anyone signing up. Invariant 5 is about the app tier holding no
state; this is the adjacent point — it should not hold *waits* either.

**Retries are bounded and only on refusal.** `EmailNotSent` means the provider
did not accept the message, so retrying is the right answer. Anything else is a
bug in our own code and retrying it three times just produces three
tracebacks.

**At-least-once, and this file says so rather than implying otherwise.** Celery
with `acks_late` will redeliver a task whose worker died after the provider
accepted the message, and nothing here can tell that apart from a task that
never ran. Preventing it needs either state we deliberately do not keep
(ADR-020 §8) or a provider-side idempotency key we do not have yet. The
consequence is a duplicate verification email, which is a nuisance rather than
a hazard — and it is written down here so that the day it becomes a hazard,
nobody has to rediscover why.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.notifications.providers.base import EmailNotSent, OutboundEmail
from apps.notifications.providers.django_email import email_provider

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    autoretry_for=(EmailNotSent,),
    retry_backoff=True,
    retry_jitter=True,
)
def deliver_email(self, *, to: str, subject: str, body: str) -> None:
    """Hand one message to the provider.

    Takes plain arguments rather than a model id, unlike the media and
    transcription tasks. There is no row to read: nothing is persisted about an
    email (ADR-020 §8), so the message has to travel in the payload. That is
    also why the body is built by the caller — a task that rendered a template
    would need the template to still mean the same thing when the task runs.
    """
    provider = email_provider()
    provider.send(OutboundEmail(to=to, subject=subject, body=body))

    # The address is not logged. It is personal data, this log is shipped
    # somewhere, and "an email was sent" is the operationally useful half.
    logger.info(
        "email_delivered",
        extra={"event": "email_delivered", "subject": subject, "provider": provider.name},
    )
