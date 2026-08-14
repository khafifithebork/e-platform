# Language Learning Platform

A curated, admin-approved language-course subscription platform. Video and audio
lessons with reviewed transcripts, progress tracking, and a single subscription
tier gated by a central entitlement resolver.

> **Status: M0 — Planning & Foundations, in progress.**
> There is no application code yet: no models, no migrations, no endpoints.
> The commands below are marked with what actually works today.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django + DRF, ASGI (Gunicorn + Uvicorn workers) |
| Frontend | Next.js App Router, TypeScript, Tailwind |
| Database | PostgreSQL |
| Jobs | Celery + Redis |

Python 3.12 · Node 22 · PostgreSQL 16.

Managed providers are selected but not yet integrated: Neon (Postgres),
Cloudflare R2 (storage), Mux (video), Deepgram (transcription), Resend (email),
Cloudflare (DNS/WAF/edge), Sentry. **The payment provider is an open decision —
see `docs/adr/001-architecture.md` §2.5. Do not model billing.**

## Repository layout

```
backend/          Django project — apps/, config/, tests/
frontend/         Next.js application            (created in M0 task T6)
infra/            Deployment configuration       (platform manifests: M13)
scripts/          Operational scripts
docs/             Architecture, deployment strategy, ADRs, STATUS
.github/          CI workflows                   (created in M0 task T10)
```

The application directories under `backend/apps/` exist as structure only. They
contain no Python modules yet and are not installed apps.

## Documentation

Read these before changing anything. `CLAUDE.md` is the operating brief and
takes precedence over the design documents.

| Document | Covers |
|---|---|
| `CLAUDE.md` | Invariants, approval gates, milestone order, definition of done |
| `docs/architecture.md` | Domain model, API design, security plan, testing strategy |
| `docs/deployment-strategy.md` | Infrastructure providers, cost modelling, video analysis |
| `docs/adr/` | Architecture decision records — later ADRs beat earlier ones |
| `docs/STATUS.md` | Current milestone, blockers, next action |

`docs/adr/002-cost-reliability-streaming.md` supersedes all cost figures
elsewhere.

## Commands

Defined in `CLAUDE.md` §12 and implemented by the `Makefile` in M0 task T11.
None of them work yet.

```
make dev            docker compose up: postgres, redis, mailpit, api, web, worker
make test           full suite
make test-fast      backend unit tests only
make lint           ruff + tsc + eslint
make migrate        apply migrations
make types          regenerate OpenAPI schema -> frontend TypeScript types
make check-deploy   manage.py check --deploy
```

`make migrate` and `make types` will remain non-functional through M0 by design:
M0 creates no models and no API schema.

## Licence

Not yet determined.
