# ADR-025 — Hosting: B-lite

**Status:** accepted
**Date:** 2026-08-28
**Decides:** CLAUDE.md §11 #3, open since M0
**Depends on:** ADR-001 §2.3 (deferral), ADR-002 §6 and §8 (recommendation),
`docs/spikes/opennext-on-workers.md` (validation)

---

## Decision

**B-lite.** Next.js on Cloudflare Workers via OpenNext; Django, Celery and
Redis on a single Hetzner CX33 managed with Dokploy; Postgres on Neon.

ADR-002 §8 recommended exactly this and attached one condition — validate the
Workers adapter with a spike before committing. **That spike ran on
2026-08-27** and the adapter builds this application.

---

## Why the deferral could end

ADR-001 §2.3 deferred the choice deliberately: containerise for both, decide at
M13 on evidence. The evidence now exists.

- **The technical risk ADR-002 attached to B-lite is largely absent.** Measured
  across every file in `frontend/src`: no `node:` builtins, no Route Handlers,
  no `middleware.ts`, no server-side `cookies()` or `headers()`. The adapter
  constrains almost nothing this application does.
- **The build succeeds**, and six of seven routes were already static before
  M15. After M15 the whole public surface is.
- **ADR-002 Move 1 — "make the public surface static" — is done**, and ADR-002
  called it not optional either way. M15 delivered it and CI verifies it against
  Next's own manifests.

**What the spike did not decide, and was never going to:** ADR-002 §6 is
explicit that the tiebreaker between B and B-lite is a preference about how you
want to spend your time, not a technical finding — roughly $6/month separates
them. That preference has now been stated.

---

## What this commits us to

### Prerequisites the spike found

- **Next must go to 16.3.3.** `@opennextjs/cloudflare@1.20.4` declares
  `peer next@">=15.5.24 <16 || >=16.3.3"`, and this project pins `16.3.1` —
  inside the excluded gap, so `npm install` refuses outright. Two patch
  releases, not a migration.
- **`opennextjs-cloudflare migrate` writes `open-next.config.ts` and
  `wrangler.jsonc`**, and both must be committed.
- **Release builds want a Linux host.** OpenNext warns on every invocation that
  it is not fully compatible with Windows. CI is Linux, so the deploy path is
  unaffected — but this project is developed on Windows, and building a release
  natively is not the supported path.
- **The adapter's dependency tree is large** — 670 packages, pulling
  `@opennextjs/aws` and AWS SDK packages beneath it. `npm audit` runs against
  all of it in CI.

### The unknown that remains

**The `/api/*` rewrite has not been proven through a running Worker.** The
build produces a Worker; it does not prove the proxy behaves. The check is not
that a request arrives but that **the session cookie survives the round trip in
both directions** — invariant 9 depends on it. Perhaps thirty minutes with
`wrangler dev` against a live Django, and it is the last thing standing between
this decision and provisioning.

### A constraint M15 discovered, which lands squarely here

**The API origin is baked into the release image.** `next.config.ts` proxies
`/api/*` with an `afterFiles` rewrite, and Next serializes rewrites into
`routes-manifest.json` as an absolute URL. Setting `API_ORIGIN` at runtime does
nothing; one image cannot be promoted across environments. See
`docs/specs/m15-public-catalogue.md` §4.3.

Under B-lite this is **an argument for answering §11 #4 as path routing**: a
Worker owning `/api/*` at the edge does not have this property at all, because
the routing lives in the Worker rather than in the Next build. The spike said
choosing B-lite would likely answer §11 #4 as a side effect; this is the
mechanism by which it does. **It is not answered here** — it is a separate
decision with its own consequences for session cookies.

---

## What this does *not* authorise

**Spend.** M13 §5.2 is a separate §5 gate and remains unanswered. Choosing the
option is not approving the bill, and nothing may be provisioned — no Hetzner
box, no Cloudflare account, no Neon project — until it is.

---

## Consequences

- **§11 #3 is closed.** M13 T7–T10 and M14 T7–T10 are unblocked *by this
  decision* and still blocked by spend.
- **§11 #5 stays moot and stays conditional.** No Server Component fetches
  Django, and M15's structural tests now enforce that for the `(marketing)`
  group. It un-moots the moment a request-time server fetch is added anywhere.
- **"Rebuilt on publish" becomes buildable.** Invariant 15's second half was
  blocked on not knowing what a deploy hook would be. Under B-lite it is a
  Workers build triggered from CI. `docs/specs/m15-public-catalogue.md` §4.2
  records where the trigger belongs: in `catalog.services.approve`, queued
  rather than inline, and debounced.
- **The ops-time disagreement is now ours to settle by doing it.** ADR-001 §2.3
  flagged that `deployment-strategy.md` §12 rates VPS ops at 8–15 h/month while
  ADR-002 §5 rates a comparable setup at 3–6 — a factor of three, unresolved,
  and the axis ADR-002 §6 calls the tiebreaker. Nothing measured it because
  nothing could. It will be measurable after a few months of running this.

---

## Alternatives rejected

| Option | Why not |
|---|---|
| **B — Render** | ~12% more expensive at MVP and ~60% more at Scenario 2, with a worse availability profile for anonymous traffic. Chosen against on preference, not on a defect. |
| **B-HA — redundant VPS** | ADR-002 puts the second node and load balancer at Scenario 2. Buying redundancy before there is traffic to protect is spending against a hypothesis. |
| **Defer again** | The deferral was itself the M0 decision and it has now run its course: the spike is done, the public surface is static, and M13 T7–T10 have been blocked on this since M13 began. |
