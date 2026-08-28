# ADR-024 — How the public catalogue stays static

**Status:** accepted
**Date:** 2026-08-28
**Milestone:** M15
**Supersedes:** nothing. **Superseded by:** nothing.

---

## Context

CLAUDE.md invariant 15 says public routes are statically generated and the
`(marketing)` route group must not depend on a live API call at request time.
Until M15 the group did not exist, so the rule constrained nothing.

Building it forced three questions that will be re-argued by anybody who adds a
page to that group, because in each case the obvious answer is the forbidden
one.

The rule is not a performance preference. `architecture.md` §3.2 has Server
Components fetching Django "over the private network", and ADR-001 §2.3 records
that B-lite — Next on Cloudflare Workers, Django on Hetzner — **has no private
network**. A request-time fetch from a public page would cross the public
internet and need its own authentication. CLAUDE.md §11 #5 is moot precisely
because no such fetch exists, and each decision below is about keeping it that
way.

---

## Decision 1 — filters are client-side over baked data, not `searchParams`

**`/courses` reads every published course at build time and filters in the
browser.**

The obvious implementation is `?language=es&level=A1` read from `searchParams`
in the server component. That opts the route into dynamic rendering: no
prerender, a server invocation per request. It is one line, it looks
idiomatic, and it silently removes the property this whole group exists to
have.

**What it costs:** filter state is not in the URL, so a filtered view cannot be
linked or bookmarked. That is a real loss and it is not hidden — the source
says so.

**What to do when it matters:** filters as route segments —
`/courses/spanish/a1` with `generateStaticParams` — which is linkable *and*
static. Not a query string.

**Why this works here at all:** the catalogue is curated and admin-approved, so
it is tens of courses, not millions. Shipping all of them to the browser is
cheap. If that stops being true, the answer is the route-segment form above,
and the person who notices the page weight makes that call.

---

## Decision 2 — search calls the API from the browser

**The search box fetches `/api/v1/catalogue/search/` after hydration.**

This does not violate invariant 15. The invariant is about *server rendering* —
a page that fetches while responding cannot be prerendered. This fetch happens
in the visitor's browser, same-origin through the Next rewrite, after the
static HTML has been delivered. `/courses` still prerenders, and its HTML still
carries every course.

**The alternative was substring-matching the baked catalogue in JavaScript.**
It needs no network. It is also strictly worse at the thing search is for: M11
built Postgres full-text search with weighted ranking — title A, skill areas B,
description C — and trigram similarity so a typo still finds the course. A
client-side `includes()` has none of that, and would make M11 dead code.

**Two consequences that shaped the implementation, both load-bearing:**

- **The endpoint is throttled at 30/min**, because a ranked query over a GIN
  index is the most expensive thing an anonymous visitor can ask this service
  to do. A request per keystroke exhausts that in eight characters. Hence a
  400ms debounce and a two-character minimum — not polish, a budget.
- **Responses can arrive out of order.** A slow answer to "spa" landing after a
  fast answer to "spanish" shows the wrong results while the box says
  otherwise. Every request carries an `AbortController` and the previous one is
  cancelled. This only happens on a slow connection, which is where nobody
  develops.

---

## Decision 3 — the price is one nullable constant, not markup

**`PRICE_BOOK` in `src/lib/pricing.ts` is `null`, and `/pricing` renders an
unannounced state.**

CLAUDE.md §11 #1 is unresolved: the payment provider and operating jurisdiction
are undecided, Stripe is unavailable to Moroccan merchants, and a merchant of
record may be required — which changes who the contracting party is, whether a
figure is VAT-inclusive, and what the refund terms must say. §6 forbids
inventing any of it.

Both states are built and tested. The priced state is exercised with a price
book that exists only in tests. **The point is that pricing day is a one-line
edit rather than a page built under time pressure**, which is when a mistake in
it is most expensive.

Two guards, because a price is the single most natural thing to add to a
landing page:

- A **structural test** over the public surface fails on a currency symbol next
  to a digit, in either order, with comments stripped so the pages may explain
  the absence.
- A **tripwire test** asserts `PRICE_BOOK` is still null. It is meant to be
  deleted, once, deliberately, in the same commit that sets a price — a visible
  act in a diff somebody reviews as a business decision.

---

## Decision 4 — the invariant is checked against the build, not the source

**`npm run verify:static` compares Next's own manifests in CI.**

Every other check for invariant 15 greps page files for `searchParams`, a
`fetch` call, or a `dynamic` export. Those are proxies. They cannot see a route
that went dynamic for a reason nobody wrote down — a dependency reading
headers, a Next default changing in a minor release, a `cookies()` call three
components deep.

**The specific gap that made this necessary:** removing
`export const dynamicParams = false` from `courses/[slug]` leaves the printed
route table **byte-identical**. Verified twice. The only place the difference
appears is `prerender-manifest.json`, where `fallback` flips from `false` to
`null`. `next build` exits 0 either way.

Without that line, a slug `generateStaticParams` did not return is rendered on
demand — which is both a request-time render and how an unpublished course
becomes reachable by guessing its slug.

---

## Consequences

**The frontend build now needs a live API and a database.** The frontend CI job
gained Postgres, Redis and a Django it starts itself. The alternative — mocking
the fetch — would mean the build never exercises the thing invariant 15 exists
to guarantee, and could not fail the way an unreachable API must.

**Redis is not incidental to that.** The catalogue endpoints are throttled and
DRF keeps throttle counters in the cache.

**A course approved in Django is invisible until somebody runs a build.**
Invariant 15's second half — *"rebuilt on publish"* — is **not implemented**,
and is blocked on §11 #4: a rebuild trigger is a deploy hook, and that hook
differs entirely between Render and Cloudflare Workers. `docs/specs/m15-public-catalogue.md`
§4.2 records what is known about where it belongs.

**Accessibility is now checked in two ways nothing in this project did before**
— colour contrast computed from the design tokens, and document structure read
from the built HTML. Both found real defects; see §Notes.

---

## Alternatives rejected

| Option | Why not |
|---|---|
| **ISR with a revalidate window** | Simplest of the three, and it un-moots §11 #5: a request-time regeneration on Workers crosses the public internet to Hetzner. |
| **Rebuild webhook on publish** | The right long-term answer, and it needs the hosting decision first. |
| **`searchParams` for filters** | Linkable, and dynamic. Trades the invariant for a convenience that route segments provide without the trade. |
| **Client-side search over baked data** | No network, no ranking, no typo tolerance, and M11 becomes dead code. |
| **`axe-core` for accessibility** | Would catch more than the two checks written here. It is a §5 dependency decision nobody has made, so it was not taken unilaterally. Worth asking for. |

---

## Notes — what the accessibility pass actually found

None of this was visible before M15 T10, because nothing measured it.

- **White text on the accent measured 2.50:1 in dark mode.** `globals.css`
  claimed the accent was "dark enough for white text at AA" — true in light
  (4.74), false in dark, where the accent is a bright orange. **Every primary
  button on the site was unreadable for anyone with dark mode on.** Fixed with
  an `--color-on-accent` token: white in light, dark ink in dark (7.29).
- **`line-strong` measured 1.69:1** against its background, in both schemes.
  Form field and card borders were not perceivable boundaries. WCAG 1.4.11 asks
  3:1; they are now 3.24–3.52.
- **The accent as text measured 4.47:1** on paper — under AA by a margin too
  small to see and large enough to fail.
- **`/courses` and `/pricing` jumped from `h1` to `h3`.** Invisible on screen,
  because styling does not follow heading level; audible to anyone browsing by
  heading.
- **`/reset-password` prerendered with no `<h1>` at all.** Its content sits
  behind a `Suspense` boundary — `useSearchParams` forces the subtree to the
  client — so the static document was the fallback word "Loading…". An M2 page,
  found by a M15 check.
