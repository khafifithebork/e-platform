# Session recap — 2026-08-13 / 14

A point-in-time record of what changed and why. `docs/STATUS.md` is the living
document; read that first next session. This one exists so the reasoning
survives, not just the diff.

**Where things stand:** M0 complete and verified. M1 half done — 4 of 8 tasks.
32 commits, all pushed. 88 tests passing, ruff clean, `check --deploy` clean.

---

## 1. What was built

### M0 — Foundations (complete, 11/11, all verified by running them)

Repository skeleton, Django settings split, ASGI runtime, Celery app,
Dockerfiles for both services, docker-compose stack, `.env.example` for both,
CI workflow, Makefile.

The stack runs: six services, `postgres`/`redis`/`api`/`mailpit` healthy, the
worker connected to Redis, and a request to `/api/` on the **web** origin
answered by Django with `Server: uvicorn` — which is ADR-001 §2.1 same-origin
routing proven rather than assumed.

### M1 — Backend Foundation (4/8)

| Task | What |
|---|---|
| T1 | `core` app, abstract `TimestampedModel` and `UUIDPrimaryKeyModel` |
| T2 | DRF + drf-spectacular configured; `CACHES` → Redis |
| T3 | RFC 9457 Problem Details exception handler, 100% branch coverage |
| T4 | Cursor + page-number pagination |

**Remaining:** T5 `/healthz` · T6 `request_id` + JSON logging · T7
`/api/v1/schema/` + drift gate · T8 `make types`.

---

## 2. Decisions recorded

Four ADRs. Each exists because someone — including a future you — would
otherwise re-argue it.

| ADR | Decision |
|---|---|
| [001](adr/001-architecture.md) | Same-origin routing via Next rewrites now, Cloudflare Worker before launch · Celery Beat in-worker at one replica · hosting late-bound to M13 · ASGI from the start · **payment provider still open** |
| [002](adr/002-cost-reliability-streaming.md) | Cost correction and streaming roadmap (pre-existing) |
| [003](adr/003-m1-ships-no-models.md) | M1 creates no concrete models; the audit log moves to M2 |
| [004](adr/004-clients-branch-on-problem-type.md) | Clients branch on the RFC 9457 `type`, not the status code |

Two are worth re-reading before M2.

**ADR-003** exists because architecture.md contradicts itself across
milestones: M1 lists an audit model, M2 requires the custom `User` to exist
before the first migration, and `AuditLog` has a foreign key to `User`. M1
therefore creates nothing. A test drives the migration autodetector directly
and fails the build if anything under `apps/` grows a model.

**ADR-004** exists because DRF downgrades `NotAuthenticated` to **403** whenever
no authenticator offers a `WWW-Authenticate` header, and `SessionAuthentication`
offers none. "Log in" and "not allowed" arrive as the same status. The fix is
the `type` member — and it is the same mechanism M4 needs for entitlement
reasons, so `EntitlementDenied` will declare a `problem_type` and add
`reason`/`cta` with **no change to the handler**. A test already covers that
path.

---

## 3. Bugs found — and how each was caught

Worth reading as a group, because five of the seven share one root cause:
**the local machine had state CI did not.**

| Bug | Caught by |
|---|---|
| `local.py` hardcoded `ALLOWED_HOSTS`, silently overriding the environment — every proxied request failed `DisallowedHost` | Running the full compose stack |
| DRF installed locally but never pinned in `pyproject.toml` | CI |
| Test suite required a live Redis (throttling counts against the cache) | CI |
| `tsc --noEmit` failed on a clean checkout — `LayoutProps` is generated into `.next/types` | CI |
| Migration-check test needed a live database | Writing it |
| Migration guard exited 1 for the *wrong* reason — `scripts/` on `sys.path`, not `backend/` | Reading the output instead of the exit code |
| `base.py` never called `read_env`, so a local `.env` was ignored | Wiring up `make migrate` |

The lesson that generalises: **a green local run proves less than it appears
to.** Two techniques now catch most of it, both recorded in STATUS:

- Dependency changes: install into a **fresh** virtualenv from
  `pyproject.toml` alone. `pip install --dry-run` would not have caught the
  missing DRF import.
- Service dependencies: **stop the relevant compose service** and re-run before
  trusting a pass. `docker compose stop redis` reproduced the CI failure
  exactly.

---

## 4. Known gotchas

Things that will bite again if forgotten.

**Dependencies are baked into the image; source is bind-mounted.** Adding a
Python package and restarting the container is not enough — the venv lives in
the image at `/opt/venv`. Hit at the end of this session: `api` sat unhealthy
with `No module named 'rest_framework'` until rebuilt.

```bash
docker compose up -d --build
```

**Port 3000 is occupied** by an unrelated project on this machine
(`btpNali/Frontend/Buildflow`, `next start`). Host ports are overridable:

```bash
WEB_PORT=3001 make dev
```

**`make migrate` refuses to run** and will keep refusing until M2 defines the
custom `User`. That is the guard working, not a fault.

**`make` is not on PATH here** — MSYS2 provides `mingw32-make`. CI on Linux is
the authoritative runner.

**`gh` is not installed**, so PRs are opened manually via the compare URL.

---

## 5. Environment state, as left

- **Branch:** `feat/m1-backend-foundation`, pushed, tree clean
- Also pushed: `feat/m0-foundations`, `chore/untrack-planning-docs` (PR #1)
- **Compose stack is running** on `WEB_PORT=3001`, all six services healthy.
  Stop it with `docker compose down`
- `docs/` is tracked again, after being briefly gitignored and restored

---

## 6. Open questions, in the order they will block work

1. **Payment provider and jurisdiction** — blocks M4 schema and M8 entirely.
   Stripe does not support Moroccan merchants; a merchant of record may be
   required. Standing rule until resolved: **do not model billing.**
2. **BFF vs path routing** — blocks M2. architecture.md §3.2 describes a BFF
   while §4.3 describes routing straight to Django, as if interchangeable. The
   `afterFiles` rewrite ordering keeps both open for now.
3. **Custom `User` before `AuditLog`** — M2 must build the user model *first*.
   ADR-003 §4 records why.
4. **Live classes on the roadmap** — affects M5 modelling. Not urgent.

Documentation defects found during the audit and **not yet corrected in
source** are listed in `docs/STATUS.md`, including two arithmetic errors and an
unverified provider-capability claim about Mux audio pricing.

---

## 7. Next session

1. Read `docs/STATUS.md`.
2. Continue M1 at **T5 (`/healthz`)**. It is deliberately liveness-only, no
   database query — a health check that fails during a brief DB blip invites
   the platform to restart containers mid-incident.
3. T6 is `request_id` + structured JSON logging; the
   `observability-and-instrumentation` skill is the right one for it.
