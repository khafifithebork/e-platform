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

os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(50))
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver")
os.environ.setdefault("DATABASE_URL", "postgres://localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/1")

from .base import *

DEBUG = False
