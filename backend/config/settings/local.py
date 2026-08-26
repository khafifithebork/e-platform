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

# The browsable API is genuinely useful while developing and is deliberately
# absent from base, so it can never reach production by accident.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# Mailpit in the compose stack. Nothing leaves the machine.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)


# ---------------------------------------------------------------------------
# Throttles, relaxable for load testing — **development settings only**
#
# The public read surface is rate-limited per IP: 120/min for the catalogue,
# 30/min for search. A load test runs from one host, so with those in force it
# measures the throttle rather than the endpoint — every run would report the
# same number, which is the limit, and nothing about how the service behaves
# under concurrency. Real load arrives from many addresses.
#
# **This switch lives here and nowhere else, deliberately.** `local.py` is
# never the settings module in production, so a way to disable throttling
# cannot exist there by construction — which is a stronger guarantee than a
# flag in `base.py` that production remembers to override. `test_settings.py`
# asserts production is unaffected.
#
# Off unless explicitly asked for, and the name says what it does rather than
# reading like a tuning knob.
# ---------------------------------------------------------------------------
if env.bool("DJANGO_DISABLE_THROTTLES_FOR_LOAD_TEST", default=False):
    REST_FRAMEWORK = {
        **REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    }


# Report violations to our own endpoint while developing, so a directive that
# would break a page shows up in the console log rather than in silence.
# Production sets CSP_REPORT_URI explicitly; this is only a convenience for
# the compose stack, where the browser and Django share an origin through the
# Next.js rewrite.
CSP_REPORT_URI = env("CSP_REPORT_URI", default="/csp-report/")

if CSP_REPORT_URI:
    CONTENT_SECURITY_POLICY_REPORT_ONLY = {
        "DIRECTIVES": {
            **CONTENT_SECURITY_POLICY_REPORT_ONLY["DIRECTIVES"],
            "report-uri": [CSP_REPORT_URI],
        }
    }
