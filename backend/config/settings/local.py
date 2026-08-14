"""Local development settings.

DEBUG defaults on here and only here. Everything else stays as close to
production as is practical, so that behaviour differences surface locally
rather than on deploy.
"""

from .base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# Binding to all interfaces is required for the container to be reachable from
# the host. Local settings are never loaded in production.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]  # noqa: S104

# Mailpit in the compose stack. Nothing leaves the machine.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
