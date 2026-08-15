"""Settings shared by every environment.

Anything environment-specific belongs in ``local``, ``production`` or ``test``.

Every variable read here without a default is deliberate. A missing value must
stop the process at import, because the alternative — falling back to a
development default — is how a system ends up serving production traffic with
a known secret key.
"""

from pathlib import Path

import environ

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# ---------------------------------------------------------------------------
# Applications
#
# apps.core contains abstract base models only. ADR-003: M1 creates no concrete
# models and no migrations, because the custom User model must exist before the
# first migration is ever applied and it does not arrive until M2. A test
# asserts nothing under apps/ has pending migrations.
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
]

INSTALLED_APPS = [*DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

MIDDLEWARE = [
    # First, deliberately. A request rejected by a later middleware — a host
    # validation failure, a CSRF rejection — is exactly the kind worth
    # investigating, and it would otherwise be logged with no correlation id.
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Invariant 12: this project runs under ASGI. There is no WSGI_APPLICATION and
# no config/wsgi.py — see ADR-001 section 2.4.
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
#
# This value is effectively permanent. The first migration applied to a
# database fixes it, and changing it afterwards is a manual table rename plus a
# migration-graph rewrite plus every foreign key repointed.
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Sessions
#
# Invariants 5 and 9: the app tier is stateless and sessions live in Postgres.
# Redis is explicitly disposable, so session storage must not depend on it —
# a cache eviction should cost latency, not log every user out.
# ---------------------------------------------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Cache
#
# Invariant 5. DRF throttling counts against the default cache, and Django's
# LocMemCache default lives in process memory — throttle limits would silently
# become per-worker the moment there is more than one, which is to say they
# would stop being limits.
#
# A different Redis database from the Celery broker, deliberately. Sharing one
# means cache.clear() deletes queued tasks: the queue empties, nothing raises,
# and the work simply never happens.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL"),
    }
}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Invariant 9. The revocation argument is in architecture.md 4.2.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Deny by default: opening an endpoint must be a deliberate act, not the
    # result of forgetting a permission class.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # The browsable API is a development convenience; in production it is an
    # HTML surface that enumerates endpoints and echoes data back. local.py
    # adds it for development only.
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # RFC 9457 Problem Details, one shape everywhere (architecture.md 6.1).
    "EXCEPTION_HANDLER": "apps.core.exceptions.problem_details_exception_handler",
    # Cursor by default; page-number is opt-in per view for small admin lists.
    # A list endpoint that forgets to paginate should still not return
    # everything.
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.CursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    # architecture.md 6.4. Per-endpoint scopes — login, playback tokens,
    # progress — arrive with those endpoints.
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Language Platform API",
    "VERSION": "1.0.0",
    "DESCRIPTION": "Curated language-learning subscription platform.",
    # The schema endpoint should not describe itself.
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # Separate request and response components, so generated TypeScript does
    # not model read-only fields as required on write.
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# Celery
#
# Broker configuration only. M0 defines no tasks and no schedule; Beat is not
# wired until the first periodic task exists (ADR-001 section 2.2).
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Logging
#
# JSON to stdout, one object per line, every line carrying a request id.
# Invariant 5: the app tier writes nothing to local disk, so the platform
# collects the stream.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIDFilter"},
    },
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        # Django ships its own `django` logger with a plain-text console
        # handler. Without overriding it every Django record is emitted twice,
        # once unstructured and once as JSON, and half the output is unparseable.
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}
