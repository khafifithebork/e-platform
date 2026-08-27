"""Celery application.

M0 defines no tasks and no schedule. This module exists so that the worker
container has something to run and so the first task in M1 needs no wiring
work.

On Beat, per ADR-001 section 2.2: the decision is settled — Beat runs inside
the worker process at a single replica — but the *implementation* waits for the
first periodic task. Two reasons. Celery's default scheduler persists its
schedule to a local file, which invariant 5 forbids; the fix is
django-celery-beat, which keeps the schedule in Postgres where it is also
inspectable from Django Admin. That package brings models and migrations, and
M0 applies no migrations because the custom User model does not exist yet. So
Beat, django-celery-beat and the first periodic task all arrive together.

The worker command in docker-compose therefore has no --beat flag, and carries
a comment saying why the replica count must stay at one when it does.
"""

import os

from celery import Celery

# Matches config/asgi.py rather than manage.py: this is a container entrypoint,
# so an unset environment should demand production configuration and fail fast.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("language_platform")

# Every Django setting prefixed CELERY_ becomes Celery configuration with the
# prefix stripped: CELERY_TASK_ACKS_LATE -> task_acks_late. Keeping broker and
# reliability settings in Django settings means one place reads the environment.
app.config_from_object("django.conf:settings", namespace="CELERY")

# No targets yet — apps/ contains no installed apps. Calling it now means the
# first app with a tasks.py is discovered without touching this file.
app.autodiscover_tasks()


# ---------------------------------------------------------------------------
# request_id across the queue boundary
#
# architecture.md §3.7: the id is propagated from Next.js to Django to Celery,
# and "without this, debugging is archaeology". Django's half has existed since
# M0 and the browser's arrived with M14 T2; this is the third hop.
#
# The concrete case it exists for: an upload returns 202 and the lesson later
# has no subtitles. Without this, the task's log lines carry `-` where the id
# belongs, and nothing joins them to the request that queued the work.
#
# Signals rather than a custom Task base class, because a base class only
# applies to tasks that remember to inherit from it — and the failure of
# forgetting is silent. Signals apply to every task, including ones written
# later and ones inside third-party packages.
# ---------------------------------------------------------------------------
from celery import signals  # noqa: E402 - must follow app creation

from apps.core.logging import (  # noqa: E402 - imports Django settings indirectly
    request_id_var,
    sanitise_request_id,
)

REQUEST_ID_HEADER = "request_id"


@signals.before_task_publish.connect
def _carry_request_id(headers=None, **_kwargs) -> None:
    """Stamp the publishing request's id onto the message.

    A message header rather than a task argument, deliberately: an argument
    would change every task's signature, appear in every call site, and be
    serialised into the payload where `WebhookEvent`-style dumps would carry
    it around. Headers are metadata and every broker Celery supports carries
    them.

    Publishing outside a request — a management command, a periodic task —
    leaves the current id empty, and nothing is stamped. The consumer then
    mints one, which is the honest answer: that work did not come from a
    request.
    """
    if headers is None:
        return
    current = request_id_var.get()
    if current:
        headers[REQUEST_ID_HEADER] = current


@signals.task_prerun.connect
def _adopt_request_id(task=None, **_kwargs) -> None:
    """Adopt the publisher's id for the duration of the task.

    Sanitised on the way in for the same reason the middleware sanitises the
    inbound HTTP header: the value has travelled through a broker, and a log
    filter will write it into a log line. Trusting it because it came from our
    own queue assumes the queue cannot be written to by anything else, which is
    an assumption about deployment rather than about code.

    A task that arrives with no id gets a fresh one rather than the previous
    task's — the worker process is long-lived and a `ContextVar` set by the
    last task would otherwise leak into the next one.
    """
    inbound = getattr(getattr(task, "request", None), REQUEST_ID_HEADER, None)
    request_id_var.set(sanitise_request_id(inbound))


@signals.task_postrun.connect
def _clear_request_id(**_kwargs) -> None:
    """Leave nothing behind between tasks.

    Without this the worker's idle log lines carry whatever the last task was
    working on, which reads as though something is still happening.

    Set to empty rather than to `NO_REQUEST`: the log filter already renders an
    empty value as `-`, so writing the sentinel here would mean two places
    decide what "no request" looks like.
    """
    request_id_var.set("")
