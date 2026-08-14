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
