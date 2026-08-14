# STATUS

**Last updated:** 2026-08-13
**Updated by:** agent session (M0 T1 and T2 implemented)

---

## Current milestone

**M0 — Planning & Foundations. Complete and verified.** All 11 tasks
implemented, all 11 verified by running them.

| Task | State |
|---|---|
| T1 repository skeleton | **done** — `1ebf740`, plus `.gitattributes` in `9d1cf0d` |
| T2 backend settings split | **done** — `c322d8d` |
| T3 ASGI runtime | **done** — `196668c` |
| T4 Celery application | **done** — `48bf163` |
| T5 backend Dockerfile | **done** — `b55505b` |
| T6 frontend scaffold | **done** — `66c314b` |
| T7 frontend Dockerfile | **done** — `ff13b77` |
| T8 docker-compose | **done** — `38ca0ae`, corrected in `883c225` |
| T9 `.env.example` | **done** — `fdcb9c3` |
| T10 CI workflow | **done** — `4982b92`, fixed in `36be0e9` |
| T11 Makefile | **done** — `e9cc85e` |

### The stack, verified

All six services start. `postgres`, `redis`, `api` and `mailpit` report
healthy; the worker connects to Redis and reports ready; the web root returns
200; and a request to `/api/` on the **web** origin is answered by Django with
`Server: uvicorn` — ADR-001 §2.1 same-origin routing proven rather than
assumed.

Two bugs surfaced only here, neither visible in isolation:

- **`local.py` hardcoded `ALLOWED_HOSTS`**, silently overriding the environment
  read in `base.py`. Next forwards the rewrite destination as the Host header,
  so Django saw `api:8000` and rejected every proxied request while
  `DJANGO_ALLOWED_HOSTS` in compose did nothing. Fixed in `883c225` with a
  regression test.
- **The mailpit pin was wrong** (`v1.27`), taken from `docker manifest inspect`
  output that had already proved unreliable. The real version is **v1.30.7**,
  confirmed by running the image and pulling that exact tag.

Host ports are overridable (`WEB_PORT`, `API_PORT`, `POSTGRES_PORT`,
`REDIS_PORT`, `MAILPIT_UI_PORT`, `MAILPIT_SMTP_PORT`); container ports are
fixed. Port 3000 on this machine is held by an unrelated project.

### Verified

Backend — 27 tests pass; `ruff check` and `ruff format --check` clean across
`backend/` and `scripts/`; `manage.py check` clean; `manage.py check --deploy`
reports **no issues, 0 silenced** against production settings.

Frontend — `tsc --noEmit` clean, `eslint` clean, production build succeeds with
no warnings.

CI — workflow YAML parses into the two intended jobs. **Not** verified that the
run passes on GitHub; only a push can show that.

### Invariants now enforced by tests, not convention

| Invariant | Guard |
|---|---|
| 5, 9 — sessions in Postgres | asserts `SESSION_ENGINE` is the DB backend |
| 12 — ASGI only | asserts `config/wsgi.py` does not exist |
| 5 — no local disk writes | asserts Gunicorn logs to stdout/stderr |
| ADR-001 §2.2 — Beat deferred | asserts no beat schedule and `django_celery_beat` uninstalled |
| §6 — no values in `.env.example` | parses every env read and asserts documented, name-only |
| M2 custom User ordering | `make migrate` refuses while `AUTH_USER_MODEL` is the default |

### Version matrix (locked to what is installed, not proposed)

Python 3.12.6 · Node 22.20.0 · Docker 29.1.3 / Compose v2.40.3 · PostgreSQL 16 (target)

Django 5.2.17 · django-environ 0.14.0 · psycopg 3.3.4 · gunicorn 26.0.0 ·
uvicorn 0.52.3 · uvicorn-worker 0.4.0 · celery 5.6.3 · redis 8.1.0 ·
ruff 0.16.3 · pytest 9.1.1 · pytest-django 4.14.0 · pytest-cov 7.1.0

Deliberately absent from M0: DRF, drf-spectacular, django-celery-beat,
django-axes, argon2-cffi, Vitest.

---

## Completed

- **Documentation reorganised** into `docs/` and untracked. `docs/` is gitignored; the files remain on disk. `CLAUDE.md` stays at the repository root because the agent tooling loads it from there.

  | Was | Now |
  |---|---|
  | `phase-1-architecture.md` | `docs/architecture.md` |
  | `deployment-strategy.md` | `docs/deployment-strategy.md` |
  | `adr-002-cost-reliability-streaming.md` | `docs/adr/002-cost-reliability-streaming.md` |
  | `agent-prompts.md` | `docs/prompts/agent-prompts.md` |

  This makes the paths in `CLAUDE.md` §2 correct for the first time. The removals are staged in git but **not committed**.

- **`.gitignore` created** — `docs/`, `.env`, `.env.*` with `!.env.example`. The full ignore file lands with M0 task T1.
- **`docs/adr/001-architecture.md` written** — records the four settled decisions (same-origin routing, Celery Beat placement, hosting deferral, ASGI) and restates the payment provider as open with a standing "do not model billing" instruction.
- **M0 plan produced** — 11 tasks, ordered, with dependencies and invariant mapping. Awaiting approval.

Still no application code, no dependencies, no migrations, no tests. `backend/`, `frontend/`, `infra/`, `scripts/`, `.github/` do not exist.

---

## In progress

None. Blocked on approval of the M0 plan and the version matrix (below).

---

## Blockers

### Blocking the first M0 task

1. **Version matrix not agreed.** `pyproject.toml` and `docker-compose.yml` cannot be pinned without Python, Django, Node, Next.js, PostgreSQL and Redis versions. Proposed defaults are in the M0 plan §8; they need confirming or correcting.
2. **Dependency approval.** `CLAUDE.md` §5 requires approval for every dependency. M0 needs roughly nine runtime and six dev packages. The list is in the M0 plan §8. Decide once whether `docs/architecture.md` counts as a standing allowlist, or this recurs every milestone.

### Open decisions (`CLAUDE.md` §11)

| # | Decision | State |
|---|---|---|
| 1 | Payment provider & jurisdiction | **Open.** Blocks M4 schema and M8. Does not block M0–M3. Standing rule: do not model billing. |
| 2 | Same-origin routing | **Settled** — ADR-001 §2.1. Next.js rewrites now, Cloudflare Worker before launch. |
| 3 | Celery Beat placement | **Settled** — ADR-001 §2.2. In-worker, single replica. `--beat` and `django-celery-beat` land with the first periodic task, not in M0. |
| 4 | Hosting target | **Settled as deferred** — ADR-001 §2.3. Containerise for both; decide at M13. |
| 5 | Live classes on the roadmap | **Open.** Blocks nothing until M5. |

`CLAUDE.md` §11 still lists 2, 3 and 4 as open and should be updated.

### New questions raised by ADR-001, deliberately left open

- **BFF vs path routing (M2).** `architecture.md` §3.2 and §4.3 describe two different architectures as if interchangeable. Resolve at M2 kickoff, before auth flows are written.
- **Private network under B-lite (M13).** Server Components fetching Django "over the private network" does not hold if Next.js is on Cloudflare Workers and Django is on Hetzner.

### Documentation defects, not yet corrected in source

- `docs/deployment-strategy.md` §9.3/§14 total the recommended (Mux) stack at ~$62; the line items sum to ~$43. The $62 figure models Cloudflare Stream.
- `docs/adr/002-...` §7.1 audio-mode saving computes to ~$612, not ~$570; §5 B-HA column sums to $152, not $157, and mixes Scenario 1 and Scenario 2 figures.
- Neon is modelled at $15 throughout, against the documents' own derivation of ~$19–20.
- Mux's 1/10 audio rate is claimed for a playback *mode*; it appears to apply to audio-only *assets*. Untagged and unsourced — verify before budgeting.
- `Brainstormv1.md` is cited by section throughout `deployment-strategy.md` and is not in the repository.

---

## Next action

1. Confirm CI passes on GitHub for `feat/m0-foundations`. The type-check fix in
   `36be0e9` has not yet been *observed* passing — it is the last unverified
   thing in M0, and only GitHub can show it.
2. Start **M1 — Backend foundation**: core app, DRF, `drf-spectacular`,
   `/healthz`, Problem Details error shape, structured logging with
   `request_id`.
3. **Answer the custom-User ordering question before writing the `core` app.**
   It is the first decision M1 needs and the most expensive one to get wrong.

### Carried into M1, recorded so it is not rediscovered

- **Custom User ordering.** M1 builds a `core` app with an audit model; M2
  builds the custom User. As written, M1's first migration lands before the
  custom model exists. Either `AUTH_USER_MODEL` and a minimal `User` move into
  M1 ahead of `core`, or M1 ships only abstract base models. Decide at M1
  kickoff. `make migrate` currently refuses, which buys the time to decide.
- **`citext` for email** (architecture.md §5.2) does not exist in Django 5.2 —
  `CITextField` was removed in the 5.x line. Use `UniqueConstraint(Lower(...))`
  or a non-deterministic collation at M2.
- **UUIDv7** (architecture.md §5.2) needs PostgreSQL 18; the target is 16. Use
  UUIDv4 unless the Postgres version changes.
- **BFF vs path routing** stays genuinely open. The `afterFiles` rewrite
  ordering in `next.config.ts` keeps both possible — a Route Handler under
  `src/app/api/` wins, anything else falls through to Django.
- **Gunicorn `timeout` vs Server-Sent Events** (ADR-002 §7.4) are in direct
  tension. Revisit when the first SSE endpoint exists.
