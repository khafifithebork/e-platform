# Spike — running this Next.js app on Cloudflare Workers (OpenNext)

**Date:** 2026-08-27
**Requested by:** ADR-002 §3 Move 2 — *"Validate this with a spike in M0 before
committing — an hour of work that de-risks the decision."*
**Blocks:** CLAUDE.md §11 #4 (hosting target), and therefore M13 T7–T10.

---

## Why this document exists

ADR-002 recommends **B-lite** — Next.js on Cloudflare Workers, Django on a
Hetzner box — and attaches one condition: validate the Workers adapter with a
spike *before* committing. **That spike was never run.** M13 T1 found the gap
while writing the deployment spec; it is the fifth instance of the pattern
ADR-023 §1 names, and the first found before anything was built on top of it.

**The question is narrower than "does Next.js run on Workers".** It is: does
*this* application, with the routing and the surface it actually has, run on
Workers — and if not, what would have to change.

---

## Finding 1 — a version gap blocks it today, and the fix is two patch releases

`@opennextjs/cloudflare@1.20.4` declares:

```
peer next@">=15.5.24 <16 || >=16.3.3"
```

This project pins `next@16.3.1`. **That falls in the excluded gap** — above 16,
below 16.3.3 — so `npm install` refuses outright:

```
npm error ERESOLVE unable to resolve dependency tree
npm error Found: next@16.3.1
npm error Could not resolve dependency:
npm error peer next@">=15.5.24 <16 || >=16.3.3" from @opennextjs/cloudflare@1.20.4
```

**`16.3.3` is the current stable release of Next**, so this is a two-patch
bump, not a migration. It is not a reason to reject B-lite; it is a
prerequisite with a known, small cost.

Worth noticing for its own sake: the exclusion of `16.0–16.3.2` is the adapter
telling you those releases had something it could not support. Whatever that
was, we are one patch below the boundary.

---

## Finding 2 — none of the constraints ADR-002 warned about apply to this app

ADR-002 §3 hedged with: *"Some Node APIs and long-running route handlers are
constrained."* Both concerns are real in general. **Neither touches this
codebase.** Measured across all 16 files in `frontend/src`:

| What OpenNext constrains | Present here? |
|---|---|
| `node:` builtins (`fs`, `path`, `crypto`, `stream`) | **None.** Zero imports. |
| Route Handlers (`route.ts`) | **None exist.** |
| `middleware.ts` | **Does not exist.** |
| Server-side `cookies()` / `headers()` | **Not used.** |
| `export const runtime` / `dynamic` overrides | **None.** |

The only `process.env` read in application code is
`NEXT_PUBLIC_PLAYBACK_URL_TEMPLATE`, which Next inlines at build time and which
never executes on a server at all.

The surface is **6 client components** and **4 server files** — two layouts and
two pages. That is a thin server-side footprint by any measure, and it is thin
in exactly the dimension the adapter cares about.

**This is the substantive result of the spike.** The risk ADR-002 attached to
B-lite was that the adapter might not support what we do. What we do is almost
nothing that it constrains.

---

## Finding 3 — the one thing that genuinely needs proving is the rewrite

`next.config.ts` proxies the API to Django:

```ts
afterFiles: [{ source: "/api/:path(.*)", destination: `${apiOrigin}/api/:path` }]
```

This is ADR-001 §2.1's same-origin routing — the reason session cookies stay
simple — and it is **the only server-side behaviour the application has.**
Everything else is static output or client-side fetching.

So the spike's real question reduces to: *does an `afterFiles` rewrite to an
external origin behave correctly on Workers, preserving cookies and headers in
both directions?*

**This also collides with §11 #2**, which is still open: same-origin routing via
Next rewrites *or* via a Cloudflare Worker doing path routing. On B-lite those
stop being alternatives — the Worker is already there, and routing `/api/*` at
the edge is a configuration rather than a rewrite. **Choosing B-lite very
likely answers §11 #2 as a side effect**, and that is worth deciding
deliberately rather than discovering.

---

## Finding 4 — the adapter's dependency footprint is larger than it looks

Installing `@opennextjs/cloudflare` pulls `@opennextjs/aws` and, through it,
AWS SDK packages including `@aws-sdk/client-dynamodb` — the install failed once
while fetching exactly that.

This is not a defect; OpenNext's Cloudflare adapter is built on its AWS
implementation. But it is a fact worth knowing before adopting it: the
dependency tree is not small, and `npm audit` runs against it in CI (M12 T4).

---

## The build attempt

**Not completed on this machine, and the reason is local rather than
architectural.**

Three separate installs failed against the npm registry with `ECONNRESET` and
`ETIMEDOUT` — the same network unreliability that also defeated two Docker
builds of the frontend image during M13 T4, where CI then built the same image
without trouble. The adapter and its tree were still installing when this was
written.

**What that means for the decision: nothing.** Findings 1–3 are static facts
about this repository and the adapter's published metadata; none of them
depends on a successful build. What a completed build would add is confirmation
that the rewrite in Finding 3 behaves, which is the one open question.

### To finish it, on a machine with a reliable connection

```bash
cp -r frontend /tmp/spike && cd /tmp/spike
npm install next@16.3.3 @opennextjs/cloudflare wrangler
npx opennextjs-cloudflare build
npx wrangler dev            # then exercise /api/* against a running Django
```

The check that matters is not that it builds. It is that a request to
`/api/v1/auth/me/` through `wrangler dev` reaches Django **and returns the
session cookie unchanged**.

---

## What this means for the hosting decision

**The spike does not decide it, and was never going to.** ADR-002 §6 is
explicit that the tiebreaker between B and B-lite is a preference about how you
want to spend your time, not a technical finding — $6/month separates them.

What the spike does is remove the technical unknown that ADR-002 attached as a
condition:

- **The blocker it found is small and known:** upgrade Next by two patches.
- **The risk it was written to investigate is largely absent:** this app uses
  almost none of what the adapter constrains.
- **One question remains open** — the external rewrite — and it is testable in
  minutes by anyone with a working npm connection.

**B-lite is not de-risked to zero, but it is no longer blocked on an unknown.**
It is blocked on a decision, a spend approval, and one thirty-minute check.
