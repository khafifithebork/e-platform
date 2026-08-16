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
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/1")

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
