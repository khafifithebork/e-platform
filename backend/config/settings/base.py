"""Settings shared by every environment.

Anything environment-specific belongs in ``local``, ``production`` or ``test``.

Every variable read here without a default is deliberate. A missing value must
stop the process at import, because the alternative — falling back to a
development default — is how a system ends up serving production traffic with
a known secret key.
"""

from pathlib import Path

import environ
from celery.schedules import crontab
from csp.constants import NONE, SELF

# Safe to import from settings: this module reads no setting and imports no
# Django machinery, only the vendor SDK and the request-id contextvar.
from apps.core.observability import initialise_error_reporting

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
    # Not `django.contrib.admin`: this AppConfig swaps in an AdminSite that
    # requires a verified OTP device (architecture.md §8). Listing it here is
    # what makes 2FA unavoidable rather than per-ModelAdmin.
    "apps.core.admin_apps.HardenedAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Ships with Django; no new dependency. Provides SearchVectorField,
    # GinIndex and the CONCURRENTLY index operations M11 needs.
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "axes",
    # Two-factor authentication for the admin site (architecture.md §8). Only
    # TOTP is enabled: static tokens are a recovery mechanism this project has
    # no process for yet, and an unused recovery path is a second way in.
    "django_otp",
    "django_otp.plugins.otp_totp",
    # Beat's schedule, in Postgres rather than in a local file (ADR-001 §2.2 and
    # invariant 5). Brings models and migrations, which is why it arrives with
    # the first periodic task rather than at M0.
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.entitlements",
    "apps.media_assets",
    "apps.transcripts",
    "apps.learning",
    "apps.notifications",
]

INSTALLED_APPS = [*DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

MIDDLEWARE = [
    # First, deliberately. A request rejected by a later middleware — a host
    # validation failure, a CSRF rejection — is exactly the kind worth
    # investigating, and it would otherwise be logged with no correlation id.
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Immediately after SecurityMiddleware, which is where the rest of the
    # response security headers are set. It only adds a header, so ordering is
    # not a correctness question — keeping the header-setting middleware
    # together is so the next person looking for "where are the headers" finds
    # them in one place.
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Immediately after authentication, and the order is the control: it reads
    # the session for a confirmed device and attaches `is_verified()` to the
    # user. Before AuthenticationMiddleware there is no user to verify, and
    # `is_verified()` would not exist for the admin site to consult.
    "django_otp.middleware.OTPMiddleware",
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

# The origins a browser may send an unsafe request from.
#
# Required, not optional, because we sit behind a proxy: Next.js forwards the
# rewrite destination as the Host header — the same fact the ALLOWED_HOSTS
# comment in local.py records — so Django's idea of its own origin is `api` or
# the internal hostname, never the `localhost:3000` or `lingua.example` the
# browser actually posted from. Django compares the two and rejects every POST,
# PUT and DELETE with "Origin checking failed".
#
# Empty by default so that nothing is silently trusted, and so a deployment
# that forgets it fails loudly on the first write rather than trusting a
# guessable origin. Every environment behind the proxy must set it.
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

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
# Entitlements
# ---------------------------------------------------------------------------
# How long a PAST_DUE subscription keeps access. A business decision with
# revenue consequences both ways — too short and a failed card locks out a
# paying customer mid-lesson, too long and access continues after payment
# stops. Seven days covers a typical card retry cycle (ADR-010 section 3).
#
# A setting rather than a literal so the boundary is a tested value and
# changing it is configuration, not a code change.
ENTITLEMENT_GRACE_PERIOD_DAYS = env.int("ENTITLEMENT_GRACE_PERIOD_DAYS", default=7)

# ---------------------------------------------------------------------------
# Media storage
#
# Any S3-compatible store. MinIO in development and CI, Cloudflare R2 in
# production (ADR-012 section 1) — the difference is the endpoint and the
# credentials, not the code.
#
# Invariant 6: the browser uploads here directly with a presigned URL. Django
# never receives the bytes.
# ---------------------------------------------------------------------------
MEDIA_STORAGE_ENDPOINT = env("MEDIA_STORAGE_ENDPOINT")
MEDIA_STORAGE_BUCKET = env("MEDIA_STORAGE_BUCKET")
MEDIA_STORAGE_ACCESS_KEY = env("MEDIA_STORAGE_ACCESS_KEY")
MEDIA_STORAGE_SECRET_KEY = env("MEDIA_STORAGE_SECRET_KEY")
# R2 ignores the region but SigV4 requires one to sign with; "auto" is what
# R2's own documentation uses.
MEDIA_STORAGE_REGION = env("MEDIA_STORAGE_REGION", default="auto")

# How long an upload URL stays valid. Long enough for a large file on a poor
# connection, short enough that a leaked URL is not a standing write grant.
MEDIA_UPLOAD_URL_TTL_SECONDS = env.int("MEDIA_UPLOAD_URL_TTL_SECONDS", default=3600)

# The cap the store cannot enforce on a presigned PUT (see providers/storage.py).
# Checked after upload, before the asset advances.
MEDIA_MAX_UPLOAD_BYTES = env.int("MEDIA_MAX_UPLOAD_BYTES", default=5 * 1024 * 1024 * 1024)

# How long a minted playback token is good for. architecture.md section 7:
# short, because a token that does not expire is a permanent share link for
# paid content, and the entitlement check that produced it becomes a one-off
# rather than a gate. Long enough that a lesson does not die mid-play.
MEDIA_PLAYBACK_TOKEN_TTL_SECONDS = env.int("MEDIA_PLAYBACK_TOKEN_TTL_SECONDS", default=4 * 60 * 60)

# How long the video provider has to fetch a master from our storage. Hours,
# not minutes: the provider queues the pull, and a URL expiring while the job
# is still queued fails an asset for no reason anyone can see.
MEDIA_SOURCE_URL_TTL_SECONDS = env.int("MEDIA_SOURCE_URL_TTL_SECONDS", default=6 * 60 * 60)

# How many times processing is retried before an asset lands in the
# dead-letter queue (the FAILED rows). Bounded: retrying forever turns a
# permanently broken asset into permanent load on the worker.
MEDIA_PROCESSING_MAX_RETRIES = env.int("MEDIA_PROCESSING_MAX_RETRIES", default=3)

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
# How many times a submission is retried before the transcript lands in the
# dead-letter queue. Bounded for the same reason as media processing:
# retrying forever turns one permanently broken asset into permanent load.
TRANSCRIPTION_MAX_RETRIES = env.int("TRANSCRIPTION_MAX_RETRIES", default=3)

# How long a rendered VTT stays in the cache. The key carries the transcript's
# updated_at, so an edit produces a different key and this is a size bound
# rather than a correctness one — a stale entry is unreachable, not wrong.
TRANSCRIPT_VTT_CACHE_SECONDS = env.int("TRANSCRIPT_VTT_CACHE_SECONDS", default=60 * 60 * 24)

# The longest manual access grant an administrator may give in one go.
#
# A guess, named rather than buried, the same way LESSON_COMPLETION_THRESHOLD
# is. The point is not the number: §5.2 rejects manual access as a boolean
# because "nobody dares remove it", and an override measured in years is that
# boolean wearing an expiry date. Ninety days is long enough for any support
# situation and short enough that somebody has to look again.
ACCESS_OVERRIDE_MAX_DAYS = 90

# Where the Django admin site is mounted. **Unset means it is not routed.**
#
# architecture.md §8: "the default /admin/ with a password is not acceptable
# for a system that can grant free access and issue refunds." A default here
# would be in the repository and therefore public, so there is none — an
# environment that has not chosen a path gets no admin site rather than a
# guessable one. `check_admin_path` refuses the obvious values.
#
# Obscurity is not the control. Staff-only and 2FA are; this only keeps the
# login form out of the way of automated scanners.
ADMIN_PATH = env("DJANGO_ADMIN_PATH", default="").strip("/")

# ---------------------------------------------------------------------------
# Learning
# ---------------------------------------------------------------------------
# What fraction of a lesson must be *watched* for it to complete itself
# (ADR-016 §2). Measured against watched time rather than the furthest
# position reached, because dragging a scrubber to the end is not watching.
#
# 0.9 is a guess. A setting rather than a literal so the boundary is a value a
# test can move and changing it is configuration.
LESSON_COMPLETION_THRESHOLD = env.float("LESSON_COMPLETION_THRESHOLD", default=0.9)

# The most watched time one heartbeat may claim. Players report every ten to
# fifteen seconds; a beat claiming more than a minute is a stuck tab or a bug,
# and letting it through makes watched_seconds meaningless for everyone who
# reads it afterwards.
PROGRESS_MAX_HEARTBEAT_SECONDS = env.int("PROGRESS_MAX_HEARTBEAT_SECONDS", default=60)

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
        # Without this, `throttle_scope` on a view is an attribute nothing
        # reads. Every per-endpoint rate below would be inert and the only
        # limit in force would be the general anonymous one — which is six
        # times more permissive than the login limit it would be replacing.
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    # architecture.md 6.4. Per-endpoint scopes — login, playback tokens,
    # progress — arrive with those endpoints.
    # architecture.md 6.4. Per-endpoint scopes are deliberately tighter than
    # the anonymous baseline: these are the endpoints worth attacking, and each
    # one either creates state or reveals whether an address exists.
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
        # The catalogue is the only surface an anonymous visitor is meant to
        # browse, and browsing means several requests per page — the general
        # anonymous limit would throttle ordinary use. A starting figure, not
        # a measured one: revisit when there is traffic to measure.
        "catalogue": "120/min",
        # Ranked full-text over a GIN index is the most expensive thing an
        # anonymous visitor can ask this service to do, and unlike browsing
        # it is not something a person does several times per page. Tighter
        # than the catalogue on purpose. A starting figure, not a measured
        # one — revisit when there is traffic to measure.
        "search": "30/min",
        # Each call signs a URL that can write to our bucket, so an
        # unthrottled version mints write grants without uploading through us.
        "media_upload": "30/hour",
        # Generous, and safe to have: a provider retries on any non-2xx, so a
        # 429 delays an event rather than losing it. Unthrottled, this is an
        # endpoint anyone on the internet can post to.
        "webhook": "600/min",
        # architecture.md §6.4 names a PlaybackTokenThrottle. Each call mints
        # signed permission to play paid content, so bulk harvesting is the
        # abuse to bound; a learner moving through a course needs only a few
        # per minute. A starting figure, not a measured one.
        "playback_token": "60/min",
        # §10 M7 names "a progress write per second" as this milestone's
        # mistake. A player beats every ten to fifteen seconds, so this allows
        # several lessons open at once while stopping a client that loops on
        # every timeupdate event.
        "progress": "40/min",
        # Trial abuse (§7.1) starts with cheap account creation.
        "register": "5/hour",
        # Credential stuffing. django-axes locks a single account; this limits
        # an attacker spraying one password across many addresses, which no
        # per-account lockout can see.
        "login": "10/hour",
        # Enumeration and mail-bombing: this endpoint sends an email to any
        # address supplied, so it is a spam vector as well as an oracle.
        "password_reset": "5/hour",
        "password_change": "5/hour",
        # Generous: the frontend calls this on load and after every auth
        # transition, so a tight limit would break normal use.
        "me": "120/min",
        "resend_verification": "3/hour",
        # No account to lock out here, so the rate limit is the only brake on
        # guessing a token.
        "verify_email": "10/hour",
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
# Beat is wired here as of M14 T4, which is the first periodic task — the point
# ADR-001 §2.2 said it would arrive. Until then this block was broker
# configuration only.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Let Django's LOGGING configuration apply inside the worker.
#
# Celery replaces the root logger's handlers on startup by default, which
# silently undoes everything `LOGGING` sets up: the worker then writes plain
# text, without the JSON formatter and — the part that matters — without the
# `RequestIDFilter`. architecture.md §3.7 asks for structured JSON carrying a
# `request_id` propagated from Next.js through Django to Celery, and with the
# hijack in place the third hop is invisible even when it works.
#
# Found exactly that way in M14 T2: the id was verified present in the queued
# message, and absent from every worker log line, because the worker was not
# using our formatter at all.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# Beat keeps its schedule in Postgres, not on disk.
#
# Celery's default `PersistentScheduler` writes `celerybeat-schedule` to the
# local filesystem, which invariant 5 forbids: the app tier is stateless, and a
# container that loses that file loses its record of when each job last ran.
# `DatabaseScheduler` puts it in the database, where it survives a redeploy and
# is inspectable from Django Admin.
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# The schedule lives in settings even though the scheduler reads the database.
#
# `DatabaseScheduler` syncs `beat_schedule` into its tables on startup, so this
# dict is the source of truth and the database is its projection. The
# alternative — creating `PeriodicTask` rows through Admin — means the schedule
# exists only in production, is not in code review, and is not in the backup
# anybody thought to test.
CELERY_BEAT_SCHEDULE = {
    "entitlement-drift-alert": {
        "task": "apps.entitlements.tasks.alert_on_entitlement_drift",
        # 06:00 UTC daily. ADR-002 §4 calls this "nightly"; an hour where a
        # European operator is awake beats one where the alert waits eight
        # hours to be read, and the job is a handful of counting queries so
        # there is no load argument for the small hours.
        "schedule": crontab(hour="6", minute="0"),
    },
    "stuck-transcription-alert": {
        "task": "apps.transcripts.tasks.alert_on_stuck_transcriptions",
        # 06:15, a quarter hour after the drift alert rather than beside it.
        # Two alerts landing in the same second read as one incident, and the
        # first thing anybody does with two simultaneous emails is assume they
        # are about the same thing.
        "schedule": crontab(hour="6", minute="15"),
    },
}

# Where operational alerts go. Empty by default, and the alert task treats that
# as "not configured" rather than guessing at an address — see M14 T4.
OPERATIONS_ALERT_EMAIL = env("OPERATIONS_ALERT_EMAIL", default="")

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

# Without this the lockout silently does nothing on a JSON API. Axes reads the
# username from request.POST, which is empty for an application/json body, so
# every attempt is recorded with username=None — the table fills, the logs look
# healthy, and the (username, ip_address) lookup never matches a real account.
AXES_USERNAME_CALLABLE = "apps.accounts.axes.get_username"

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


# ---------------------------------------------------------------------------
# Error reporting (M14 T5)
#
# Every value comes from the environment and every one has a default, so the
# absence of a Sentry account is the ordinary case rather than a broken one.
# `apps.core.observability` is the only module that names the vendor.
#
# One `init` here serves all three processes that load Django — the ASGI
# server, the Celery worker, and management commands — because the Django and
# Celery integrations auto-enable from the installed packages.
#
# **The free tier's quota is the spend cap.** Sentry's pricing page puts "set
# maximum spend threshold" on its paid plans, and ADR-002 §5 budgets Sentry at
# $0, which is the Developer plan: 5k errors a month across everything. There
# is therefore no cap to configure, and the way to stay inside it is to send
# less — a separate DSN per service so one noisy tier can be muted alone, and
# tracing off until M14 T6 decides it is wanted. ADR-027 §2.
# ---------------------------------------------------------------------------
# The bearer token /metrics requires. Empty means the endpoint answers 404 and
# the feature is off, which is its state here: nothing scrapes it yet (M14 T6,
# ADR-028 §3). A metrics endpoint reachable without a credential publishes queue
# depth and backlog size, which is a description of how loaded this system is
# and when it is weakest.
METRICS_TOKEN = env("METRICS_TOKEN", default="")

SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="local")
SENTRY_RELEASE = env("SENTRY_RELEASE", default="")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

SENTRY_ENABLED = initialise_error_reporting(
    dsn=SENTRY_DSN,
    environment=SENTRY_ENVIRONMENT,
    release=SENTRY_RELEASE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
)


# ---------------------------------------------------------------------------
# Content Security Policy
#
# **Report-only, in both tiers** (ADR-022 §4). There is no deployment
# collecting reports until M13, so enforcing here would be enforcing a policy
# nobody has ever observed in a browser — and CSP fails silently: a wrong
# directive does not raise, it removes a stylesheet.
#
# The only HTML this tier serves is the Django admin. DRF is configured with
# `JSONRenderer` alone, so there is no browsable API to accommodate — which is
# why this policy can be tight without a long tail of exceptions.
#
# `report-uri` is read from the environment and omitted when unset. A
# report-only policy with nowhere to report is a header that costs a few bytes
# and teaches nobody anything; M13 sets the variable when there is an endpoint
# to receive them.
# ---------------------------------------------------------------------------
CSP_REPORT_URI = env("CSP_REPORT_URI", default="")

_CSP_DIRECTIVES: dict[str, list[str]] = {
    "default-src": [SELF],
    "script-src": [SELF],
    "style-src": [SELF],
    # `data:` because the admin's TOTP enrolment renders a QR code inline.
    # Narrower than it looks: it permits data URIs for images only.
    "img-src": [SELF, "data:"],
    "font-src": [SELF],
    "connect-src": [SELF],
    # Clickjacking, belt and braces with X_FRAME_OPTIONS. `frame-ancestors` is
    # the one browsers still honour when the two disagree.
    "frame-ancestors": [NONE],
    "form-action": [SELF],
    # Without this, an injected `<base>` re-points every relative URL on the
    # page — including the admin's own form actions.
    "base-uri": [SELF],
    "object-src": [NONE],
}

if CSP_REPORT_URI:
    _CSP_DIRECTIVES["report-uri"] = [CSP_REPORT_URI]

CONTENT_SECURITY_POLICY_REPORT_ONLY = {"DIRECTIVES": _CSP_DIRECTIVES}
