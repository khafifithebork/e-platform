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
    "axes",
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
    # Last, as django-axes requires: it needs the authentication middleware to
    # have run so that a failed attempt can be attributed.
    "axes.middleware.AxesMiddleware",
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
# Password hashing
#
# Argon2 first (architecture.md §4.2). It is memory-hard, so an attacker with a
# GPU farm gains far less against it than against PBKDF2, which is compute-hard
# and parallelises well.
#
# PBKDF2 stays below it and is not decoration: Django verifies an existing hash
# with whichever hasher produced it and upgrades it on the next successful
# login. Removing the old hasher would lock out every account created before
# the switch.
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# ---------------------------------------------------------------------------
# Brute-force lockout (django-axes)
#
# AxesStandaloneBackend must come first. Behind ModelBackend it would only be
# consulted after Django had already authenticated the request, which is too
# late to refuse one.
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AXES_FAILURE_LIMIT = 5

# Hours. Temporary rather than permanent on purpose: a lockout that never
# expires is a denial-of-service an attacker can trigger against any account
# whose email address they know.
AXES_COOLOFF_TIME = 1

# Both together. Keying on IP alone punishes everyone behind one NAT — a
# school or an office — for one person's typos; keying on username alone lets
# an attacker lock a known account out from anywhere. The pair is what makes
# the control usable.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

# The login field is the email address, not a username.
AXES_USERNAME_FORM_FIELD = "email"

# Successful logins reset the counter, so a legitimate user who mistypes twice
# and then succeeds does not carry those failures forward.
AXES_RESET_ON_SUCCESS = True

# ---------------------------------------------------------------------------
# Password validation
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
