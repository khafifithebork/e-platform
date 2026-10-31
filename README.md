# Language Learning Platform

A curated, admin-approved language-course subscription platform. Video and audio
lessons with reviewed transcripts, progress tracking, and a single subscription
tier gated by a central entitlement resolver.

> **Status:** M0–M7 and M10–M16 complete. **M14 (Observability) is 6 of 10** —
> the rest needs a deployment. **M8 (billing) and M9 (trial) are blocked on
> decisions, not on code.** See `docs/STATUS.md`.
>
> **1663 backend tests, 757 frontend across 60 files, plus 31 script-level
> guards.** The product has a public catalogue, an authenticated learner surface,
> an admin site, search, notifications, error reporting and a metrics endpoint.
> Nothing is deployed: the pipeline is built and dormant, and no account has been
> provisioned.
>
> **An invited private beta is in progress** on a separate track from the
> milestones — see `tasks/plan.md` and `tasks/todo.md`. Invitation persistence,
> the audited issue/revoke/consume services and invitation-only registration are
> merged; the operator surface and the signup copy are not yet. **The gate is
> off:** `BETA_INVITATION_REQUIRED` defaults to `False`, so registration is open
> until somebody turns it on, which the plan treats as a release admission policy
> needing its own approval.

## Quick start

Requires Docker, and Python 3.12 / Node 22 if you want to run tests outside the
containers.

```bash
make dev
```

That generates a local `.env` with fresh secrets (idempotent — it never
overwrites an existing key) and starts seven services:

| Service | URL | Notes |
|---|---|---|
| web | http://localhost:3000 | Next.js. `/api/*` is proxied to Django |
| api | http://localhost:8000 | Django under Uvicorn |
| worker | — | Celery, with Beat embedded at one replica |
| postgres | localhost:5432 | Set `POSTGRES_PORT` if a native Postgres already holds it |
| redis | localhost:6379 | Broker on db 0, cache on db 1 |
| storage | localhost:4566 | S3-compatible store (LocalStack). Presigned uploads are exercised for real |
| mailpit | http://localhost:8025 | Catches all outbound mail |

Host ports are overridable when something else already holds one:

```bash
WEB_PORT=3001 make dev
```

**Run the suite with the storage service up.** Object-storage tests skip when
nothing answers, and each skip waits for a connection to time out first — a full
run against a dead store measured 963s against 82s with it running.

**It is LocalStack, not MinIO, since 2026-09-25**, and the pinned version and the
`S3_SKIP_SIGNATURE_VALIDATION=0` beside it are both load-bearing — `latest` is
licence-gated, and without the flag two presigned-tampering tests pass without
checking anything. `docker-compose.yml` explains both; MinIO gated its images on
Docker Hub and then on quay.io within eleven days.

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
| `make test` | Everything: backend suite, frontend tests, type-check and lint |
| `make test-fast` | Backend tests only |
| `make lint` | ruff + tsc + eslint |
| `make check-deploy` | `manage.py check --deploy` |
| `make schema` | Regenerate `docs/openapi.yaml` from the code |
| `make types` | Regenerate the schema, then the frontend TypeScript types |
| `make migrate` | Apply migrations |

Management commands worth knowing, all read-only unless stated:

| Command | What it does |
|---|---|
| `report_metrics` | Queue depth, webhook lag, transcription age. `--prometheus` prints exactly what `/metrics` serves |
| `reconcile_entitlements` | Where subscription state has drifted. Reports; never repairs |
| `check_database` | Pre-deploy probe: extensions, permissions, connection shape |
| `predeploy` | Migrations under an advisory lock it verifies is actually held. **Writes** |
| `backfill_search_vectors` | Chunked, idempotent backfill for the search index. **Writes** |

Frontend verification beyond the type-check. **Each of these reads build output,
not source**, so they must run after `npm run build`:

| Command | What it checks |
|---|---|
| `npm run verify:static` | Invariant 15 — public routes prerender — against Next's own manifests |
| `npm run verify:a11y` | Document structure in the **built** HTML, not the source |
| `npm run verify:css` | Every design-token reference resolves; no bare custom-property values |
| `npm run verify:bundle` | 350 KB first-load budget per route, with floors so it cannot pass by measuring nothing |
| `npm run test:scripts` | The guard scripts' own tests. `npm test` runs these after vitest |

**Run them against a fresh build.** They read `.next/`, so a stale one makes them
describe a tree that no longer exists — which has produced a false green here.

The dependency audit is its own CI job rather than a step inside the frontend one.
`frontend/scripts/assert-dependency-audit.mjs` wraps `npm audit --audit-level=high`
and honours `frontend/audit-allowlist.json`, where an exception needs an exact
dependency path, a named triager and a review date that **fails the gate when it
expires**. It was a step until an unfixable advisory turned the whole job red and
skipped the eleven checks behind it, so a red audit no longer hides whether the
code works.

On Windows `make` is not on PATH; MSYS2 provides `mingw32-make`. CI runs on
Linux and is the authoritative runner.

## Gotchas

**Adding a Python dependency needs an image rebuild.** Source is bind-mounted so
code changes appear live, but the virtualenv lives inside the image at
`/opt/venv`. Symptom is a container that will not start with
`ModuleNotFoundError`. This has now happened twice — `django-csp` in M12 and
`sentry-sdk` in M14 — which is why CI builds and smoke-tests the release image.

```bash
docker compose up -d --build
```

**A green local test run proves less than it looks.** Two failures reached CI
this way. Verify dependency changes by installing into a *fresh* virtualenv from
`pyproject.toml` alone, and verify service-dependency changes by stopping the
relevant compose service and re-running.

**Vitest does not type-check.** A green frontend run says nothing about whether
the build compiles; `tsc --noEmit` has caught what 300+ passing tests did not,
twice. `make test` runs both.

**Settings fail fast.** A missing environment variable stops the process at
import rather than defaulting. That is intended — see
`backend/config/settings/base.py`.

**`pytest.mark.django_db` wraps every test in a transaction, which hides whether
your code opened one.** So a service that *must* run inside a caller's
transaction passes its tests either way — removing `@transaction.atomic` from a
service left 22 tests green while breaking it under production autocommit. Any
transactional guarantee needs `django_db(transaction=True)` to be asserted at
all; under plain `django_db` you are testing a transaction pytest supplied.

**`auto_now_add` is only as precise as the OS clock.** Three back-to-back
`timezone.now()` calls return the *same* timestamp on Windows (~0.9ms
resolution), so `ordering = ["-created_at"]` is not a total order and tied rows
come back in a different order per query — which breaks pagination, not just
tests. Order by a tiebreaker as well. Note the keys here are random UUIDv4s, so
a key tiebreaker gives you *stability*, not chronology.

**Do not run `npm run build` on the host while the web container is running.**
Both write to `frontend/.next/` through the bind mount and corrupt each
other's generated route types — the symptom is TypeScript errors inside
`.next/dev/types/routes.d.ts`, which is a generated file nobody wrote. Stop the
container first, or build inside it.

**A native Postgres will silently win port 5432.** A Windows PostgreSQL service
bound to `0.0.0.0:5432` takes IPv4 loopback ahead of Docker's mapping. The
symptom is baffling: `psql` works *inside* the container while the host gets
`password authentication failed` with the same credentials. Set `POSTGRES_PORT`
in the root `.env` — the compose file already reads it.

## Layout

```
backend/          Django — apps/, config/, tests/
frontend/         Next.js App Router
infra/            Deployment config — cloudflare/, hetzner/, neon/, docs/
scripts/          Operational scripts
docs/             Architecture, ADRs, specs, runbooks, spikes, STATUS
```

## Documentation

`CLAUDE.md` is the operating brief and takes precedence over the design
documents. Later ADRs beat earlier documents.

| Document | Covers |
|---|---|
| `CLAUDE.md` | Invariants, approval gates, milestone order, definition of done |
| `docs/STATUS.md` | Current milestone, blockers, next action — **read first** |
| `tasks/plan.md` | The invited private beta: slices, acceptance, dependencies |
| `tasks/todo.md` | Which beta slices are done. Unchecked means not done, not permission to do |
| `docs/architecture.md` | Domain model, API design, security plan, testing strategy |
| `docs/deployment-strategy.md` | Providers, cost modelling, video analysis |
| `docs/adr/` | Decision records. **Later ones win** |
| `docs/specs/` | Per-milestone specifications and abuse cases |
| `docs/runbooks/` | Rollback and accessibility verification. **Each says whether it has actually been walked** — assume not until it does |
| `docs/spikes/` | Research that informed a decision |
| `infra/docs/provisioning.md` | What to create, in what order, what it costs |
| `infra/docs/deploying.md` | What happens on a merge, and what must exist first |
| `docs/SESSION-RECAP.md` | What changed recently and why |

`docs/adr/002-cost-reliability-streaming.md` supersedes all cost figures
elsewhere.

## Deployment

**Decided, built, and dormant.** ADR-025 chose B-lite: Next.js on Cloudflare
Workers, Django/Celery/Redis on one Hetzner CX33 under Dokploy, Postgres on
Neon. Roughly $44/month at MVP.

Every deploy job is gated on the repository variable `DEPLOY_ENABLED`, which is
unset, because nothing has been provisioned. `infra/docs/deploying.md` has the
sequence and the list of what a human has to do first — starting with setting a
required reviewer on the production environment, **before** switching the
pipeline on.

## Architecture in one paragraph

Django owns all data and serves JSON; Next.js renders and proxies `/api/*` to
it, so the browser sees one origin and session cookies stay simple. Media never
passes through Django — uploads go browser-to-R2 presigned, playback goes
browser-to-CDN signed. Access is decided by a single entitlement resolver that
returns a reason rather than a boolean, built and tested against a fake billing
provider in M4 *before* a real payment provider is integrated in M8. The
architectural invariants are non-negotiable and listed in `CLAUDE.md` §4.

## Licence

**Proprietary. All rights reserved.** See `LICENSE`.

No licence is granted to copy, modify, distribute or reverse-engineer any part of
this repository. Access — including through a fork — does not confer a right to
use it. Third-party dependencies remain under their own licences.

> The repository is public while this is read. **It is intended to be private**;
> changing that is a repository-settings action, and a fork taken before the
> change stays with whoever took it.
