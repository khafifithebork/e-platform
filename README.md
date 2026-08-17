# Language Learning Platform

A curated, admin-approved language-course subscription platform. Video and audio
lessons with reviewed transcripts, progress tracking, and a single subscription
tier gated by a central entitlement resolver.

> **Status:** M0 and M1 complete. **M2 (Authentication & Accounts) in progress —
> 4 of 10.** See `docs/STATUS.md`.
>
> Registration, email verification and session hardening exist. Login, password
> reset and `/auth/me/` do not yet.

## Quick start

Requires Docker, and Python 3.12 / Node 22 if you want to run tests outside the
containers.

```bash
make dev
```

That generates a local `.env` with fresh secrets (idempotent — it never
overwrites an existing key) and starts six services:

| Service | URL | Notes |
|---|---|---|
| web | http://localhost:3000 | Next.js. `/api/*` is proxied to Django |
| api | http://localhost:8000 | Django under Uvicorn |
| mailpit | http://localhost:8025 | Catches all outbound mail |
| postgres | localhost:5432 | Set `POSTGRES_PORT` if a native Postgres already holds it |
| redis | localhost:6379 | Broker on db 0, cache on db 1 |
| worker | — | Celery, no tasks yet |

Host ports are overridable when something else already holds one:

```bash
WEB_PORT=3001 make dev
```

To run the backend tests directly, create a virtualenv and install from
`backend/pyproject.toml`:

```bash
python -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"
```

## Commands

| Command | Status |
|---|---|
| `make bootstrap` | Generate the local `.env`. Idempotent |
| `make dev` | Start the stack. Runs `bootstrap` first |
| `make test` | Backend suite, plus frontend type-check and lint |
| `make test-fast` | Backend tests only |
| `make lint` | ruff + tsc + eslint |
| `make check-deploy` | `manage.py check --deploy` |
| `make schema` | Regenerate `docs/openapi.yaml` from the code |
| `make types` | Regenerate the schema, then the frontend TypeScript types |
| `make migrate` | Apply migrations. The M0 guard now permits it — `AUTH_USER_MODEL` is set |

On Windows `make` is not on PATH; MSYS2 provides `mingw32-make`. CI runs on
Linux and is the authoritative runner.

## Gotchas

**Adding a Python dependency needs an image rebuild.** Source is bind-mounted so
code changes appear live, but the virtualenv lives inside the image at
`/opt/venv`. Symptom is a container that will not start with
`ModuleNotFoundError`.

```bash
docker compose up -d --build
```

**A green local test run proves less than it looks.** Two failures reached CI
this way. Verify dependency changes by installing into a *fresh* virtualenv from
`pyproject.toml` alone, and verify service-dependency changes by stopping the
relevant compose service and re-running.

**Settings fail fast.** A missing environment variable stops the process at
import rather than defaulting. That is intended — see
`backend/config/settings/base.py`.

**A native Postgres will silently win port 5432.** A Windows PostgreSQL service
bound to `0.0.0.0:5432` takes IPv4 loopback ahead of Docker's mapping. The
symptom is baffling: `psql` works *inside* the container while the host gets
`password authentication failed` with the same credentials. Set `POSTGRES_PORT`
in the root `.env` — the compose file already reads it.

## Layout

```
backend/          Django — apps/, config/, tests/
frontend/         Next.js App Router
infra/            Deployment config (platform manifests land at M13)
scripts/          Operational scripts
docs/             Architecture, deployment strategy, ADRs, STATUS
```

## Documentation

`CLAUDE.md` is the operating brief and takes precedence over the design
documents. Later ADRs beat earlier documents.

| Document | Covers |
|---|---|
| `CLAUDE.md` | Invariants, approval gates, milestone order, definition of done |
| `docs/STATUS.md` | Current milestone, blockers, next action — **read first** |
| `docs/SESSION-RECAP.md` | What changed recently and why |
| `docs/architecture.md` | Domain model, API design, security plan, testing strategy |
| `docs/deployment-strategy.md` | Providers, cost modelling, video analysis |
| `docs/adr/` | Decision records |

`docs/adr/002-cost-reliability-streaming.md` supersedes all cost figures
elsewhere.

## Architecture in one paragraph

Django owns all data and serves JSON; Next.js renders and proxies `/api/*` to
it, so the browser sees one origin and session cookies stay simple. Media never
passes through Django — uploads go browser-to-R2 presigned, playback goes
browser-to-CDN signed. Access is decided by a single entitlement resolver that
returns a reason rather than a boolean, built and tested against a fake billing
provider in M4 *before* a real payment provider is integrated in M8. The
architectural invariants are non-negotiable and listed in `CLAUDE.md` §4.

## Licence

Not yet determined.
