# STATUS

**Last updated:** 2026-08-17
**Updated by:** agent session (M2 complete)

---

## Current milestone

**M2 — Authentication & Accounts. Complete — 10 of 10.**
Branch: `feat/m2-authentication`.

Spec: `docs/specs/m2-authentication.md`
Decisions: `docs/adr/005-m2-authentication-decisions.md`,
`docs/adr/006-security-controls-must-be-provoked.md`

| Task | State |
|---|---|
| T1 custom `User` + first migration | **done** — `da72ff4` |
| T2 Argon2, session settings, `django-axes` | **done** — `07ebd47` |
| T3 account creation service | **done** — `1243253` |
| T4 registration + email verification | **done** — `abb7938` |
| T5 login / logout / CSRF bootstrap | **done** — `f189a68` |
| T6 password reset + confirm + change | **done** — `fa7daed` |
| T7 `GET /auth/me/` | **done** — `5805353` |
| T8 throttle scopes provoked and tested | **done** — `74f42ed` |
| T9 frontend auth flows + design foundation | **done** — `245d226` |
| T10 ADR, schema and types | **done** |

**252 tests pass**, ruff clean, tsc clean, `check --deploy` clean.

### All eight abuse cases are covered

Every case in `docs/specs/m2-authentication.md` now has a passing test. The
enumeration one includes the variant that matters most: a second registration
for a taken address does **not** overwrite the existing password.

### Two controls were configured and inert — read ADR-006 before M4

The `django-axes` lockout (T5) and every per-endpoint rate limit (T8) were
correctly configured, read correctly in review, and did nothing. Neither was
caught by review, types, or any functional test — only by a test that tried to
trip the control and saw it fail to trip.

**ADR-006 makes provoking a control the standard**, and it exists because M4's
entitlement resolver and M8's webhook signature check would fail the same way,
far more expensively: an inert entitlement check gives the product away, an
inert signature check makes the webhook a free-subscription API.

### ADR-005 §2.1 validated end to end

No BFF layer. Verified through the running stack: `csrf` sets the cookie,
register returns 202, login returns 200 and sets `sessionid`, `/auth/me/`
returns the right user — all through the Next rewrite.

Also landed: `21bad4c` fixed the bootstrap gap — `make bootstrap` now writes
`backend/.env` as well as the root one, so `make migrate` and local
`manage.py` work without exporting variables by hand.

**204 tests pass**, ruff clean, tsc clean, `check --deploy` clean.

### Tests now need Postgres

M2 is the first milestone with models. CI runs Postgres as a service
(`b36bdbb`) — chosen over SQLite deliberately, because the schema depends on a
functional unique constraint now and JSONB and full-text search later, so a
SQLite pass would prove nothing about production.

**Local gotcha, cost an hour:** a native **PostgreSQL 18 Windows service** on
this machine binds `0.0.0.0:5432` and wins over Docker's mapping for IPv4
loopback. Auth succeeded *inside* the container and failed from the host with
the same credentials. The compose stack now uses **`POSTGRES_PORT=5433`** (set
in the root `.env`). Third collision of this kind, after port 3000 and the
home-directory lockfile.

### The threat model is the spec

`docs/specs/m2-authentication.md` lists eight abuse cases. Three are now
covered:

- **1 — enumeration.** A taken address is indistinguishable from a free one at
  registration, *and* a second attempt does not overwrite the existing
  password. The second half is the one that would have been account takeover.
- **3 — privilege escalation.** `role`, `is_staff`, `is_superuser` and
  `is_email_verified` in a request body reach nothing: the serializer declares
  two fields, so there is no path from the wire to them.
- **4 & 5 — token replay and expiry.** Verification tokens are stored hashed,
  single-use and expiring. Unknown, expired and already-used give one
  indistinguishable answer, so a failed guess yields no information.

**Not yet proven: abuse case 6** (lockout not bypassed by changing User-Agent),
which lands with T5, and **7 and 8**, which land with T7.

### Milestone-order guards have now fired, all correctly

- The M0 `make migrate` guard refused for the whole of M1 and now permits.
- The M0 test asserting the default user model was written to fail *exactly
  once*, as a reminder to come back. It did, and has been replaced.
- The M1 schema drift gate failed the moment endpoints existed — and exposed
  something larger than drift: drf-spectacular cannot infer request bodies from
  a plain `APIView`, so generated types would have been empty and invariant 16
  satisfied in name only. Views are annotated; types describe real operations.

---

## M1 — Backend Foundation. Complete — 8 of 8.

| Task | State |
|---|---|
| T1 core app + abstract base models | **done** — `fae22ac` |
| T2 DRF + drf-spectacular configuration | **done** — `616eede`, pins fixed in `9f630ec` |
| T3 Problem Details exception handler | **done** — `0b565bb`, problem types in `ca56c72` |
| T4 pagination classes | **done** — `0616c15` |
| T5 `/healthz` | **done** — `9050775` |
| T6 `request_id` middleware + JSON logging | **done** — `c5eb681` |
| T7 `/api/v1/schema/` + drift gate | **done** — `38eb242` |
| T8 frontend type generation (`make types`) | **done** — `38eb242` |

### A redirect loop found by verifying, not by testing

`/api/v1/schema/` through the Next.js rewrite bounced forever: Next 308'd it to
`/api/v1/schema`, Django's `APPEND_SLASH` 301'd it back. **Every endpoint in
architecture.md §6.2 ends in a trailing slash**, so this would have broken all
of them from M2 onwards.

Two causes, both fixed in `next.config.ts`:

- Next's default `trailingSlash: false` strips the slash before the rewrite
  runs. Now `trailingSlash: true`, aligning with Django rather than disabling
  canonical redirects on the static marketing surface (invariant 15).
- The rewrite used `:path*`, which splits on `/` and swallows the terminal
  slash. Now `:path(.*)`, a greedy capture that forwards the path verbatim.

Verified through the running stack: with slash, without slash, and the
marketing root all return 200. **No automated test covers this** — it needs
both services running, so it belongs in the Playwright journeys at M12. Worth
adding there explicitly.

### Known and unresolved

One plain-text duplicate line appears per Django log record in the container.
The logger tree was probed in place and is correct — root and `django` both on
`JsonFormatter`, `django.request` propagating with no handlers of its own — so
the source is elsewhere, most likely uvicorn's own logging config. **Cosmetic
log volume, not correctness:** the correlated JSON line is present and right.
Timeboxed after three diagnostic rounds per `CLAUDE.md` §9.

**ADR-003** settles that M1 creates no concrete models and no migrations; the
audit log moves to M2, after the custom `User`. A test drives the migration
autodetector directly and fails the build if anything under `apps/` grows a
model.

**ADR-004** settles that clients branch on the RFC 9457 `type` member rather
than the status code, because DRF downgrades `NotAuthenticated` to 403 when no
authenticator offers a `WWW-Authenticate` header — so "log in" and "not
allowed" share a status. The same mechanism carries M4's entitlement reasons:
`EntitlementDenied` will declare a `problem_type` and add `reason`/`cta`
without the handler changing.

88 tests pass, ruff clean, `check --deploy` clean, 100% branch coverage on the
exception handler.

### Three CI failures, all the same root cause

Both were environment drift — the local machine had state CI did not, and both
are now guarded:

- **DRF installed but not pinned** in `pyproject.toml`. Fixed in `9f630ec`.
  Standard now: verify dependency changes by installing into a *fresh*
  virtualenv from `pyproject.toml` alone, not with `--dry-run`.
- **The suite required a live Redis**, because T2 pointed `CACHES` at Redis and
  DRF throttling counts against the default cache. It passed locally only
  because the compose stack was running. Fixed in `6a6e600`: test settings use
  `LocMemCache`, and the production assertions moved to a subprocess check
  against production settings. Reproduce this class of failure by stopping the
  relevant compose service before trusting a green local run.
- **`REDIS_CACHE_URL` was never added to the CI workflow.** T2 added it as a
  required variable and taught `.env.example`, `test.py` and
  `docker-compose.yml` about it — but not `ci.yml`, so `check --deploy` died
  with `ImproperlyConfigured`. Fixed **and guarded** in `0e9b4fe`: a test parses
  `ci.yml`, extracts what the deployment step supplies, and compares it against
  every default-less `env()` read in `base.py`. **This class of drift is now
  caught by the suite** rather than by CI.

---

## M0 — Planning & Foundations. Complete and verified.

All 11 tasks implemented, all 11 verified by running them.

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

## Next milestone: M3 — Catalogue & Course Domain

`Language`, `Course`, `Section`, `Lesson`; the draft/review/publish state
machine; slugs and ordering; instructor CRUD scoped to their own courses;
Django Admin configured.

Two things to carry in from M2:

- **ADR-006 applies to M3's scoping.** `architecture.md` §10 M3 names the
  failure directly: letting instructors query courses without a `get_queryset()`
  scope filter. Write the IDOR test first, and make it fail before the filter
  exists.
- **`AuditLog` is M10**, not M3 (ADR-005 §3 amending ADR-003).

Still blocking, unchanged: **the payment provider decision** gates M4's schema
and M8 entirely. Standing rule until resolved — **do not model billing.**

## Earlier next-action notes

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
