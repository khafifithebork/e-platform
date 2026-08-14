"""Local development settings.

DEBUG defaults on here and only here. Everything else stays as close to
production as is practical, so behaviour differences surface locally rather
than on deploy.
"""

from pathlib import Path

import environ

# django-environ does not read a .env file unless asked, and this has to happen
# before base is imported, because base reads the variables at import time.
#
# It belongs in local settings only. Production and the containers receive
# their configuration from the platform, and a .env file silently overriding
# that would be a genuinely confusing failure to debug.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
environ.Env.read_env(_BACKEND_ROOT / ".env")

# E402: the import genuinely must follow read_env above, because base reads its
# environment variables at import time.
from .base import *  # noqa: E402

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# ALLOWED_HOSTS is deliberately NOT set here. base reads it from
# DJANGO_ALLOWED_HOSTS, and a hardcoded list in this module silently overrode
# that: the compose stack reaches Django as `api`, because Next.js forwards the
# rewrite destination as the Host header, and every proxied request failed with
# DisallowedHost while the variable in docker-compose.yml did nothing.
#
# With DEBUG on and no value set, Django already permits localhost, 127.0.0.1
# and [::1], so running the backend directly needs no configuration either.

# Mailpit in the compose stack. Nothing leaves the machine.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
