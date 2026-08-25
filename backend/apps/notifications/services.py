"""Sending transactional email. The only caller of the task.

Invariant 2: this is where a write-shaped side effect belongs, not in a view.
The two M2 call sites reached for `send_mail` directly from `views.py`, which
put a network call in an HTTP handler and made the mail body part of the
request/response layer.

**Enqueue, never send.** Nothing in this module talks to a provider; it hands
the message to Celery and returns. A caller that wants to know whether delivery
succeeded is asking a question this design cannot answer synchronously, and the
honest response is that transactional email is asynchronous everywhere.
"""

from __future__ import annotations

from apps.notifications.tasks import deliver_email


def send_transactional_email(*, to: str, subject: str, body: str) -> None:
    """Queue one message for delivery.

    Returns nothing, deliberately. A task id would be a handle to something no
    caller can usefully do anything with — there is no result backend
    (`CELERY_RESULT_BACKEND = None`), so it could not be polled even if
    somebody wanted to.
    """
    deliver_email.delay(to=to, subject=subject, body=body)
