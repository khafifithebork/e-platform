# Spike — running this Next.js app on Cloudflare Workers (OpenNext)

**Date:** 2026-08-27
**Result:** the adapter builds this application. One prerequisite, one unknown.
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
AWS SDK packages including `@aws-sdk/client-dynamodb` — one of the failed
installs died fetching exactly that. The successful run added **670 packages
and took 23 minutes** on this connection.

This is not a defect; OpenNext's Cloudflare adapter is built on its AWS
implementation. But it is a fact worth knowing before adopting it: the
dependency tree is not small, and `npm audit` runs against it in CI (M12 T4).

---

## The build — it works

**`opennextjs-cloudflare build` succeeds on this application.** Completed on
2026-08-27 after three failed installs; the fourth took 23 minutes and 670
packages, and the network, not the adapter, was what took the time.

```
next@16.3.3 + @opennextjs/cloudflare@1.20.4
$ npx opennextjs-cloudflare migrate   # generates open-next.config.ts + wrangler.jsonc
$ npx opennextjs-cloudflare build     # exit 0
...
Worker saved in `.open-next/worker.js`
```

**The route table is the most useful thing it produced:**

```
┌ ○ /                      ○ (Static)   prerendered
├ ○ /_not-found            ○ (Static)
├ ○ /forgot-password       ○ (Static)
├ ƒ /learn/[lessonId]      ƒ (Dynamic)  server-rendered on demand
├ ○ /login                 ○ (Static)
├ ○ /register              ○ (Static)
└ ○ /reset-password        ○ (Static)
```

**Six of seven routes are already static.** Only the lesson page renders on
demand. That is Finding 2 restated by the build itself, and it bears directly
on ADR-002 Move 1 — *"make the public surface static"*, which that ADR calls
not optional either way. The public surface substantially **already is**;
what is missing is the marketing and catalogue pages that do not exist yet.

Build output is 24 MB in `.open-next/`, dominated by Next's own compiled
server runtime rather than by application code.

### Two things the build said that are worth quoting

**OpenNext warns it is not fully compatible with Windows.** Verbatim, on every
invocation:

> `WARN OpenNext is not fully compatible with Windows.`
> `WARN For optimal performance, it is recommended to use Windows Subsystem for Linux (WSL).`
> `WARN While OpenNext may function on Windows, it could encounter unpredictable failures during runtime.`

It built anyway, and the warning is about the *build host*, not the deploy
target — Workers run the output regardless. But this project is developed on
Windows, so anyone adopting B-lite should expect to build releases in WSL or
in CI rather than natively. **CI is Linux, so the deploy path is unaffected.**

**`migrate` writes two files** — `open-next.config.ts` and `wrangler.jsonc` —
and both would need to be committed. Its closing note flags that the cache
needs configuring separately, which is unexplored here and is the next thing
to look at if B-lite is chosen.

### Still not verified: the rewrite through a running Worker

The build produces a Worker; it does not prove the `/api/*` proxy behaves.
That needs `wrangler dev` running against a live Django, and the check is not
that a request arrives but that **the session cookie survives the round trip
in both directions**. Perhaps thirty minutes, and it is the one remaining
unknown.

---

## Two decision inputs found after the spike, in ADR-001

Both were written down at M0 and neither was carried into the M13 planning
until 2026-08-27.

### The ops-time estimate is contested by a factor of three

ADR-001 §2.3 flags it explicitly, and it is the axis ADR-002 §6 calls the
tiebreaker:

> *"the two documents disagree about that cost by a factor of three
> (`deployment-strategy.md` §12 rates VPS ops at 8–15 h/month; ADR-002 §5 rates
> a comparable setup at 3–6 h/month). That disagreement is unresolved and is
> exactly the input the decision needs."*

**M13's spec quoted only ADR-002's 3–6 figure**, in a table, as though it were
settled. It is not. If B-lite's real cost is 8–15 hours a month, that is a
different decision from the one the $6/month price gap suggests — and nothing
in this spike measures it, because it cannot be measured without running it.

### ADR-001 named a B-lite blocker this spike did not set out to check

> *"`architecture.md` §3.2 has Next.js Server Components fetching Django 'over
> the private network'. B-lite puts Next.js on Cloudflare Workers and Django on
> Hetzner — different providers, no private network. Server-side fetches would
> cross the public internet and need their own authentication. ADR-002 does not
> address this. It is not an M0 problem; it is an M13 blocker and it is written
> down here so it is not discovered then."*

**Checked, and it is currently moot.** No Server Component fetches Django. The
only `await` in a server file is Next's async `params`, which is not a network
call — every fetch in the application is client-side, from the browser, through
the same-origin rewrite.

Two caveats worth keeping:

- **Static generation keeps it moot.** A catalogue page built with
  `generateStaticParams` fetches at *build* time, which happens in CI, not on
  Workers. ADR-002 Move 1 and this blocker resolve each other.
- **It stops being moot the moment a request-time server fetch is added.** That
  is now recorded in CLAUDE.md §11 as a standing condition rather than a
  one-time check.

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

**B-lite is no longer blocked on an unknown.** The adapter builds this
application, six of its seven routes are already static, and the only
prerequisite found is a two-patch Next upgrade. What remains is a decision, a
spend approval, one thirty-minute cookie check, and the knowledge that release
builds want a Linux host — which CI already is.
