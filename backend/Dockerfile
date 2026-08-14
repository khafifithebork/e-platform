# syntax=docker/dockerfile:1

# Backend image. Two runnable targets:
#
#   --target dev      uvicorn with reload, for docker compose
#   --target runtime  gunicorn with uvicorn workers, for deployment
#
# ADR-001 section 2.3 keeps the hosting target late-bound, so this image is the
# deployment contract and must work unchanged on Render or on Dokploy.

# ---------------------------------------------------------------------------
# Dependencies
#
# Split from the source copy so the expensive layer is keyed on pyproject.toml
# alone. Editing a Python file then costs a cache hit, not a reinstall.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY pyproject.toml ./

# A virtualenv rather than a system install, purely so the whole dependency
# tree is one directory that later stages can copy in a single layer.
# psycopg[binary] ships wheels, so no compiler or libpq headers are needed.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install .

# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root from here down. A container process that does not need root should
# not have it, and this is the cheapest hardening available.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

USER app
EXPOSE 8000

# ---------------------------------------------------------------------------
# Development
#
# uvicorn directly rather than manage.py runserver: runserver is a WSGI path,
# and invariant 12 says this project runs under ASGI. Reload works because the
# compose file bind-mounts the source over /app.
# ---------------------------------------------------------------------------
FROM base AS dev

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM base AS runtime

CMD ["gunicorn", "-c", "gunicorn.conf.py", "config.asgi:application"]
