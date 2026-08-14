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

# Binding to all interfaces is required for the container to be reachable from
# the host. Local settings are never loaded in production.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]  # noqa: S104

# Mailpit in the compose stack. Nothing leaves the machine.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
