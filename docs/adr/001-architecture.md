# ADR-001 — Baseline Architecture and the M0 Decisions

**Status:** Accepted
**Date:** 2026-08-12
**Supersedes:** nothing
**Related:** `docs/architecture.md` (the full design), `docs/deployment-strategy.md` (provider research), `docs/adr/002-cost-reliability-streaming.md` (cost correction and streaming roadmap; authoritative on all cost figures)

---

## 1. Context

`docs/architecture.md` proposed a Django + DRF backend, a Next.js App Router frontend, PostgreSQL, and Celery + Redis, deployed as three processes with video, transcription, email and payments delegated to managed providers. It left four decisions marked ⚠️ and deferred them to the project owner. `docs/adr/002-cost-reliability-streaming.md` then corrected the cost model and proposed an alternative hosting shape.

Nothing has been built. This ADR records the architecture as approved and closes four of the five open questions so that M0 can proceed. It exists because in six months nobody — including the people who made these calls — will remember why.

A note on ordering: this ADR is numbered 001 but was written after ADR-002. ADR-002 was authored against `architecture.md` before the ADR sequence existed. The numbering reflects logical dependency, not chronology.

---

## 2. Decision

Proceed with the architecture as specified in `docs/architecture.md`, subject to the corrections in ADR-002, with the following five points settled.

### 2.1 Same-origin routing — Next.js rewrites now, Cloudflare Worker before launch

**Decision.** `next.config` proxies `/api/*` to Django. The browser sees one origin. Before launch, a Cloudflare Worker (or Origin Rule) takes over the `/api/*` split and the rewrite is removed.

**Why.** Session cookies are only simple when the browser sees a single origin, and both alternatives cost something we do not want to pay yet. Subdomains plus CORS (option C in `architecture.md` §4.3) means maintaining CORS config, `CSRF_TRUSTED_ORIGINS` and credentialed-request rules — a reliable source of "works locally, fails in production". The Worker is genuinely better and removes a network hop, but it is a production-edge concern that cannot be exercised in local development and does not need to exist to write auth code. Rewrites are correct, cost nothing, and work identically in `docker compose`.

**Consequences.** Every client-initiated mutation makes one extra hop through the Next.js server, consuming its CPU. At our scale this is irrelevant. Swapping to the Worker later is a config change on both sides, not a code change — provided nothing depends on the request having passed through Next.js.

**Note for M2.** `architecture.md` §3.2 describes a BFF (browser → Next.js → Django) while §4.3 option B describes path routing (browser → Django directly for `/api/*`). These are different architectures with different session and error-shaping consequences, and the document treats them as interchangeable. The rewrite approach is BFF-shaped; the Worker approach is not. **Whether client mutations must always traverse a Next.js Route Handler is a separate question and is still open.** Resolve it at M2 kickoff, before the auth flows are written.

**Revisit when.** Before launch (M13), or sooner if the Next.js service shows CPU pressure from proxying.

### 2.2 Celery Beat — inside the worker process, single replica

**Decision.** Scheduled work runs via Beat embedded in the Celery worker (`celery worker --beat`), at exactly one replica. The service definition carries a comment stating that scaling this service past one replica causes duplicate scheduled executions.

**Why.** The alternative — platform cron jobs — moves the schedule out of the application and into provider configuration, which makes it invisible to `git`, untestable locally, and different on every hosting target. Since the hosting target is deliberately undecided (§2.3), a schedule that lives in the platform would have to be rebuilt if the target changes. Beat in the worker keeps the schedule portable.

**Consequences.** The worker becomes a singleton. Scaling job throughput means splitting Beat into its own process first — a real constraint, accepted knowingly. Duplicate scheduled executions are the failure mode if this is forgotten, and they are user-visible: double emails, double charges.

**Two implementation notes, both deliberate.**

1. **`--beat` is not wired in M0.** M0 has no scheduled tasks. Adding Beat before there is anything to schedule buys nothing and forces the next point early.
2. **Beat's default scheduler writes a local schedule file**, which conflicts with the stateless-app-tier invariant (`CLAUDE.md` §4.5, "no local disk writes"). The resolution is `django-celery-beat`, which stores the schedule in PostgreSQL and makes it inspectable from Django Admin. That package brings its own models and migrations, so it lands with the first periodic task, not in M0.

**Revisit when.** The worker becomes a throughput bottleneck, or the first periodic task is written — whichever comes first.

### 2.3 Hosting — containerise for both, decide at M13

**Decision.** M0 produces Dockerfiles and a `docker-compose.yml` that are the deployment contract. No `render.yaml`, no Dokploy configuration, no platform manifest of any kind until M13. The choice between Render (Architecture B) and Cloudflare Workers + Hetzner/Dokploy (B-lite, recommended by ADR-002 §8) is made at M13 on evidence.

**Why.** ADR-002 §6 makes the argument and it is correct: "Render or Hetzner" is a deploy target, not an architecture. The decision costs nothing to defer and everything to get wrong early, because a platform manifest written in M0 quietly becomes load-bearing. Deferring also lets the choice be made when the ops-time cost is known rather than estimated — and the two documents disagree about that cost by a factor of three (`deployment-strategy.md` §12 rates VPS ops at 8–15 h/month; ADR-002 §5 rates a comparable setup at 3–6 h/month). That disagreement is unresolved and is exactly the input the decision needs.

**Consequences.** Late binding only holds if the statelessness rules hold (`deployment-strategy.md` §7.2, `CLAUDE.md` §4.5). Sessions in PostgreSQL, uploads direct to object storage, no local disk, no in-process timers in the web tier. Break any of those and this stops being a config change.

**One thing to check before B-lite is chosen.** `architecture.md` §3.2 has Next.js Server Components fetching Django "over the private network". B-lite puts Next.js on Cloudflare Workers and Django on Hetzner — different providers, no private network. Server-side fetches would cross the public internet and need their own authentication. ADR-002 does not address this. It is not an M0 problem; it is an M13 blocker and it is written down here so it is not discovered then.

**Revisit at.** M13, informed by the OpenNext spike run during M0.

### 2.4 Django runs under ASGI from the start

**Decision.** Gunicorn with Uvicorn workers, serving `config.asgi:application`. No `wsgi.py` is created — not as a fallback, not for reference.

**Why.** ADR-002 §7.5 item 1: this is a one-line change now and a painful one after M8. Server-Sent Events for progress and processing notifications, and Django Channels if live chat ever ships, become configuration on a clean ASGI monolith and a migration on a WSGI one. There is no cost to being right early here.

**Consequences.** Any library that assumes a WSGI environment needs checking before adoption. Sync ORM calls inside async views are a real hazard and will need review discipline once views exist. `architecture.md` §9 lists `wsgi.py` in the folder structure; omitting it is a deliberate deviation, recorded here, so that reverting to WSGI requires a decision rather than an import.

### 2.5 Payment provider and jurisdiction — STILL OPEN

**Not decided.** Stripe does not support Moroccan merchants; a merchant of record (Paddle on current evidence) may be required. This determines the webhook schema, the entitlement sync model, the refund flow and the admin tooling.

**Standing instruction until it is resolved: do not model billing.** No `Plan`, no `Subscription`, no `WebhookEvent`, no provider adapter, no billing app content, no fields on any other model that exist only to serve billing. This is not a soft preference — `architecture.md` §10 M4 depends on the answer, and guessing here is the most expensive mistake available in this codebase (`CLAUDE.md` §9).

M0 through M3 do not touch billing and are unblocked. The decision must land before M4 schema work begins. It should be made during M0, which is why `architecture.md` §10 lists it as an M0 prerequisite — but no M0 deliverable depends on it, so M0 starts now.

---

## 3. Consequences overall

- M0 can start immediately. Four of five open decisions are closed; the fifth does not touch M0.
- The repository stays hosting-agnostic through M12. That is a constraint on every milestone, not just M13.
- Two questions are deliberately left open and recorded above rather than silently resolved: the BFF-vs-path-routing shape (M2) and the private-network assumption under B-lite (M13).
- `CLAUDE.md` §11 should be updated to strike decisions 2, 3 and 4, retain 1 and 5, and add the two questions above.

---

## 4. Alternatives rejected

| Question | Rejected | Why |
|---|---|---|
| Same-origin routing | Subdomains + CORS | CORS plus CSRF plus credentialed requests is a well-known production-only failure class |
| Same-origin routing | Cloudflare Worker immediately | Cannot be exercised locally; no benefit until launch traffic exists |
| Celery Beat | Platform cron | Schedule leaves the repo, differs per host, and the host is undecided |
| Hosting | Commit to Render now | Cheap to defer, expensive to unpick; the ops-cost input is disputed |
| Hosting | Commit to B-lite now | ADR-002 is Proposed, and its private-network assumption is unverified |
| Runtime | WSGI now, ASGI later | Free today, painful after M8 |
