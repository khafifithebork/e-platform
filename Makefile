# The commands CLAUDE.md section 12 promises.
#
# Recipes assume a POSIX shell. CI runs on Linux where `make` is standard. On
# Windows `make` is not on PATH — MSYS2 provides `mingw32-make`, and recipes
# that shell out may behave differently there. The authoritative runner is CI.
#
# PYTHON must point at an interpreter with the backend dependencies installed.
# Either override it, or activate the virtualenv first:
#   Linux/macOS   . backend/.venv/bin/activate
#   Windows       backend\.venv\Scripts\activate

PYTHON  ?= python
NPM     ?= npm
COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help bootstrap dev test test-fast lint migrate types check-deploy

help:
	@echo "bootstrap     generate the local .env compose needs (idempotent)"
	@echo "dev           start the local stack: postgres, redis, mailpit, api, web, worker"
	@echo "test          full suite"
	@echo "test-fast     backend tests only"
	@echo "lint          ruff + tsc + eslint"
	@echo "migrate       apply migrations (guarded until a custom User model exists)"
	@echo "types         regenerate the OpenAPI schema and frontend types"
	@echo "check-deploy  manage.py check --deploy"

# Generates the root .env with fresh secrets. Idempotent — an existing key is
# never overwritten, so it cannot rotate the database password out from under
# a running volume.
bootstrap:
	$(PYTHON) scripts/bootstrap_env.py

# Depends on bootstrap so a fresh clone needs no manual step before the stack
# will start.
dev: bootstrap
	$(COMPOSE) up

# Frontend has no test runner yet: Vitest arrives with the first component in
# M2. Until then the frontend contributes its type check and lint to the suite.
test: test-fast
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run lint

test-fast:
	cd backend && $(PYTHON) -m pytest

lint:
	cd backend && $(PYTHON) -m ruff check . ../scripts
	cd backend && $(PYTHON) -m ruff format --check . ../scripts
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run lint

# The guard refuses to proceed while AUTH_USER_MODEL is still Django's default.
# The first migrate creates auth_user, and changing the user model afterwards
# is a manual schema rewrite. It stops refusing by itself once M2 lands the
# custom model. See scripts/check_custom_user_model.py.
migrate:
	cd backend && $(PYTHON) ../scripts/check_custom_user_model.py
	cd backend && $(PYTHON) manage.py migrate

# Depends on drf-spectacular, which arrives in M1 along with the first
# endpoints. There is no schema to generate from an API that does not exist.
types:
	@echo "make types is not available yet: no OpenAPI schema before M1." >&2
	@exit 1

check-deploy:
	cd backend && DJANGO_SETTINGS_MODULE=config.settings.production $(PYTHON) manage.py check --deploy
