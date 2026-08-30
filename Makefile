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
.PHONY: help bootstrap dev test test-fast lint migrate schema types check-deploy

help:
	@echo "bootstrap     generate the local .env compose needs (idempotent)"
	@echo "dev           start the local stack: postgres, redis, mailpit, api, web, worker"
	@echo "test          full suite"
	@echo "test-fast     backend tests only"
	@echo "lint          ruff + tsc + eslint"
	@echo "migrate       apply migrations (guarded until a custom User model exists)"
	@echo "schema        regenerate docs/openapi.yaml from the code"
	@echo "types         regenerate the schema, then the frontend TypeScript types"
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

# The whole suite: backend, then the frontend's tests, types and lint.
#
# The frontend test run was missing here until M14 T6. The comment this replaces
# said "Vitest arrives with the first component in M2" — it arrived in M15 T2,
# and `make test` went on skipping 334 tests that CI was running all along. A
# command documented as the full suite has to be one, or the next person to
# trust it gets a green run that proved less than they think.
test: test-fast
	cd frontend && $(NPM) run test
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

# Regenerate the OpenAPI document. A test asserts the committed copy still
# matches the code, so this is the command that test tells you to run.
schema:
	cd backend && DJANGO_SETTINGS_MODULE=config.settings.test $(PYTHON) manage.py spectacular --file ../docs/openapi.yaml

# Invariant 16: frontend request and response types are generated from the
# schema, never hand-written. Regenerates the schema first, so the types can
# never be built from a stale contract.
types: schema
	cd frontend && $(NPM) run types

check-deploy:
	cd backend && DJANGO_SETTINGS_MODULE=config.settings.production $(PYTHON) manage.py check --deploy
