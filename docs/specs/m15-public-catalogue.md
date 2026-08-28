# M15 — Public catalogue

**Status:** approved 2026-08-27. Four decisions answered up front (§5).
**Branch:** `feat/m15-public-catalogue`
**Depends on:** M3 (catalogue domain), M11 (search and filters) — both merged.

---

## 1. Objective

**The product is visible to somebody who has not signed up.**

Today it is not. A visitor can reach a login form and nothing else. Every
catalogue endpoint the backend exposes — browse, filter, search, course detail,
related courses — has no caller.

---

## 2. What exists, measured rather than assumed

### 2.1 The backend is finished and waiting

| Endpoint | Built |
|---|---|
| `GET /api/v1/catalogue/courses/` — browse, with `language`/`level`/`skill_area` filters | M3, M11 |
| `GET /api/v1/catalogue/courses/{slug}/` — course detail | M3 |
| `GET /api/v1/catalogue/search/` — full-text, `websearch_to_tsquery` + trigram | M11 |
| `GET /api/v1/catalogue/languages/` | M3 |

`PublicCourseViewSet` sets `authentication_classes = ()` deliberately, so the
catalogue answers identically for anonymous and signed-in visitors and stays
cacheable at the edge. Its `lookup_field` comment already says what this
milestone is for: *"Slugs, not UUIDs: these are the URLs the marketing pages
are built on."* Those pages were never built.

### 2.2 The frontend is eight files

```
(auth)/login  (auth)/register  (auth)/forgot-password  (auth)/reset-password
(auth)/layout   layout   page   learn/[lessonId]
```

**There is no `(marketing)` route group.** architecture.md:937 puts *"landing,
pricing, public course pages"* in one, and CLAUDE.md invariant 15 governs how
it must behave. Neither the group nor the pages exist.

### 2.3 The test runner promised at M2 never arrived

`.github/workflows/ci.yml:259`, verbatim:

> `# There is no test runner yet — Vitest arrives with the first component in M2.`

M2 shipped. **Six client components exist.** Vitest did not arrive, and the
comment has been telling anyone who read it otherwise for twelve milestones.

That is the tenth instance of the pattern ADR-023 §1 names — a control that a
document describes and nothing implements — and it is the reason §5.2 is
answered in this spec rather than deferred again.

---

## 3. Tasks

| # | Task | Blocked? |
|---|---|---|
| T1 | This spec | no |
| T2 | Vitest + Testing Library, wired into CI | no |
| T3 | The `(marketing)` route group and its layout | no |
| T4 | Course listing, with filters | no |
| T5 | Course detail, by slug | no |
| T6 | Search UI over the M11 endpoint | no |
| T7 | Landing page | no |
| T8 | Pricing page | **partly** — see §6 |
| T9 | Build-time static generation; CI gains a live API | **partly** — see §4.2 |
| T10 | Accessibility pass, close-out, ADR | no |

---

## 4. The constraint that shapes everything

**Invariant 15:** *"Public routes are statically generated, rebuilt on publish.
The `(marketing)` route group must not depend on a live API call at request
time."*

This is not a performance preference. It is what keeps CLAUDE.md §11 #5 moot —
the private-network assumption that B-lite breaks. A build-time fetch happens
in CI; a request-time fetch on Cloudflare Workers would cross the public
internet to Hetzner and need its own authentication. The OpenNext spike
confirmed six of seven existing routes are already static; this milestone must
not be what changes that.

**So no `(marketing)` page may fetch at request time.** T9 is where that stops
being a rule and becomes something asserted.

### 4.1 What this costs CI, which is new

`generateStaticParams` fetching course slugs from Django means **the frontend
build needs a running API and a database.** The frontend CI job currently has
neither — it is `npm ci`, typecheck, lint, audit, build, with no services.

That is a real change to the pipeline and it is T9's actual work. The
alternative — mocking the fetch in CI — would mean the build never exercises
the thing invariant 15 exists to guarantee.

### 4.2 "Rebuilt on publish" is not built, and cannot be here

Invariant 15 has two halves. *"Public routes are statically generated"* is done
and now verified against the build manifest rather than the source. *"rebuilt on
publish"* is **not done**, and T9 is where that becomes visible rather than
where it gets fixed.

Today a course approved in Django is invisible to the public site until
somebody runs a build. Nothing triggers one.

**It is blocked on §11 #3 (hosting target)**, and not incidentally. A rebuild trigger is a
deploy hook, and what that hook *is* differs entirely between the two hosting
candidates — a Render deploy hook URL, or a Cloudflare Workers build triggered
from CI. Building one now means building it twice.

What can be said precisely, so nobody has to rediscover it:

- The trigger belongs in `catalog.services.approve`, which is the one place a
  course becomes public.
- It must be a queued task rather than an inline call. Invariant 8's reasoning
  applies: an approval that fails because a build service is down is an
  approval that fails for an unrelated reason.
- It must debounce. Approving five courses in a minute should produce one
  build, not five, and the natural implementation — a task per approval — does
  the wrong thing by default.

None of that is buildable before the platform is chosen. It is listed here so
that M13 T7–T10 pick it up rather than discovering it at launch.

### 4.3 The API origin is baked into the image, and that is a deployment blocker

Found on 2026-08-28, fixing the release-image build. **Not introduced by M15 —
M15 is what made it visible.**

`next.config.ts` proxies `/api/*` to Django with an `afterFiles` rewrite, which
is ADR-001 §2.1's same-origin routing. **Next serializes rewrites into the
build output.** `routes-manifest.json` from a local build reads:

```json
{ "source": "/api/:path(.*)", "destination": "http://localhost:8000/api/:path" }
```

An absolute URL, fixed at build time. Two consequences:

- **Setting `API_ORIGIN` at runtime does nothing.** The container reads it for
  nothing; the destination is already decided.
- **One image cannot be promoted across environments.** The image CI builds
  proxies `/api/*` to the CI runner's Django. Deploying that image anywhere
  else gives a site whose every API call goes to a host that does not exist.

Nothing is broken today, because M13 T4 deliberately builds the release image
and does not push it. It is a landmine rather than a fire.

**It bears directly on two open questions.** §11 #3 (hosting target) now has a
constraint attached: whatever builds the release image must reach the API at
build time, and must build one image per environment — or the API must be at a
stable public origin known at build time. §11 #4 (BFF vs path routing) is the
other half: **a Cloudflare Worker routing `/api/*` at the edge does not have
this property at all**, because the routing lives in the Worker rather than in
the Next build. That is a genuine argument for path routing that nobody had
when §11 #4 was written.

Not fixed here. The fix is a hosting decision, not a code change, and picking
one unilaterally is exactly what §5 forbids.

---

## 5. Decisions, answered 2026-08-27

| # | Question | Answer |
|---|---|---|
| 5.1 | Scope | **Public catalogue only.** The `(marketing)` group. No authed surface, no instructor UI. |
| 5.2 | Test runner | **Vitest + Testing Library.** §5 dependency approval given. |
| 5.3 | Static generation | **`generateStaticParams` against a live API in CI.** Not ISR, not a rebuild webhook. |
| 5.4 | Milestone identity | **M15, a new milestone.** The gap accumulated across M3 and M7; retro-fitting would rewrite STATUS.md's history. |

**5.3 is the one with a consequence attached.** ISR would have been simpler and
would have un-mooted §11 #5 under B-lite. The rebuild-webhook option needs the
hosting decision first, which is still open. Build-time generation is the only
one of the three that works without answering §11 #3 — and it is what the
OpenNext spike already validated.

---

## 6. What is not decided, and where it bites

**T8, pricing, has no price.** CLAUDE.md §11 #1 — payment provider and
operating jurisdiction — is unresolved, and §6 of the constitution forbids
inventing one. Stripe is unavailable to Moroccan merchants; a merchant of
record may be required, and that changes what a pricing page may legally say.

**T8 therefore builds the page and not the number.** Layout, tier structure,
trial framing, and a single place the figure lands when there is one. A page
with a fabricated price is worse than no page: it is a commitment nobody made.

---

## 7. Abuse cases — these become the first tests

1. **No `(marketing)` page fetches at request time.** Asserted structurally and
   against the build's own route table, not by reading the code.
2. **A course that is not published is not reachable**, by slug, by search, or
   by a stale statically-generated path left over from before it was
   unpublished.
3. **Course content is not leaked by the catalogue.** A public course page
   shows what the public serializer returns and nothing the entitlement
   resolver gates.
4. **A search query is not reflected into the page unescaped.** It arrives from
   a URL, it is displayed back, and §6 forbids `dangerouslySetInnerHTML` on
   user content.
5. **A hostile search query does not break the page** — the backend already
   strips control characters after `?q=%00` returned a 500 at M11; the frontend
   must not reintroduce a crash of its own.
6. **The build fails loudly if the API is unreachable**, rather than emitting a
   site with an empty catalogue. A silently empty listing is the failure this
   milestone would otherwise ship.
7. **No page requires JavaScript to show its content.** Static generation that
   renders nothing without hydration is not static generation.

---

## 8. Not in M15

- **No authed surface.** No "my courses", no progress display, no player work.
  §5.1.
- **No instructor or admin UI.** Django Admin covers the second; the first is
  its own milestone.
- **No price.** §6.
- **No Playwright.** §5.2 chose one runner; browser journeys are a separate
  decision with its own §5 gate.
- **No design system.** Tailwind is already here; a component library is a
  dependency and a decision nobody has been asked for.
