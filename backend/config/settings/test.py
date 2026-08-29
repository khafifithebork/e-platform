"""Test settings.

The suite must run with no .env file and no live services. The values seeded
below are placeholders that satisfy the fail-fast reads in ``base``; none of
them is a credential and nothing connects to them. M0 has no models, so no
test database is created.

The secret key is generated rather than written literally: CLAUDE.md section 6
forbids environment variable values in code or tests even when throwaway.
"""

import os
import secrets
from pathlib import Path

import environ

# From M2 the suite has models, so it needs a real database — the one promise
# in this module's docstring that no longer holds unqualified. Reading
# backend/.env gives a developer's local run the database `make bootstrap`
# configured, without anyone exporting DATABASE_URL by hand.
#
# read_env never overwrites a variable that is already set, so CI — which sets
# DATABASE_URL for its own Postgres service — is unaffected, and so are the
# setdefaults below.
environ.Env.read_env(Path(__file__).resolve().parents[2] / ".env")

os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(50))
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver")
os.environ.setdefault("DATABASE_URL", "postgres://localhost:5432/test")

# The MinIO container's documented defaults, not secrets: they are the same
# values printed in MinIO's own quickstart, they reach a local container only,
# and compose and CI both supply their own. Present so `pytest` on a bare
# machine still imports — the storage tests skip when nothing answers.
os.environ.setdefault("MEDIA_STORAGE_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MEDIA_STORAGE_BUCKET", "media-test")
os.environ.setdefault("MEDIA_STORAGE_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MEDIA_STORAGE_SECRET_KEY", "minioadmin")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/1")

# Assignment, not setdefault, and that is the whole point: read_env above has
# already loaded backend/.env, so a developer with a real DSN in it would
# otherwise report every deliberately-raised exception in the suite to a live
# project. The free tier allows 5k errors a month across all three services and
# this suite has over 1400 tests, so one `make test` could spend the budget.
os.environ["SENTRY_DSN"] = ""

# E402: the import genuinely must follow read_env and the setdefaults above,
# because base reads its environment at import time.
from .base import *  # noqa: E402

DEBUG = False

# Local memory, not Redis. DRF throttling counts against the default cache, so
# any test that exercises a real view opens a cache connection — and a suite
# that needs a running Redis is a suite that only passes on a machine which
# happens to have one. CI does not.
#
# The invariant-5 reason base uses Redis is about production, where per-process
# counters would stop being limits. It does not apply to a single-process test
# run. test_settings.py asserts production still uses Redis, so relaxing it here
# cannot hide a regression there.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# MD5, and only here. Argon2 is memory-hard by design — that is the whole
# reason base.py puts it first (§4.2) — and the suite creates an account in
# most of its integration tests, so the property that makes it a good password
# hasher is also what makes a full run take about an hour on a developer
# machine. A slow suite is a suite people stop running, which costs more
# security than this line does.
#
# **Nothing is given up.** The three assertions that Argon2 is configured,
# retained above PBKDF2, and actually produces an `argon2$` hash now read
# *production* settings in a clean interpreter — the same technique
# test_settings.py uses, and the same reasoning as the CACHES relaxation above.
# Relaxing this here cannot hide a regression there, and the tests were
# provoked against a PBKDF2-first base.py to confirm they still fail.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tasks run inline, because from M11 a request path enqueues one: registration
# and password reset hand their email to Celery instead of sending it in the
# view. Without this the suite needs a live broker to register an account.
#
# **This does not change how tasks are tested.** Every task test in this suite
# calls `.apply()` explicitly, which was already inline; this only affects
# `.delay()` reached through a view. The M5 finding still stands and is the
# reason for that convention: inline execution runs retries inline too, so a
# test watching for a `Retry` exception reports "did not raise" against code
# that retries correctly.
#
# `task_eager_propagates` is left at its default of False on purpose. In
# production `.delay()` returns before the task runs, so a failing email cannot
# fail a registration; propagating here would make the suite disagree with
# production about what a broken task does to the request that queued it.
CELERY_TASK_ALWAYS_EAGER = True
