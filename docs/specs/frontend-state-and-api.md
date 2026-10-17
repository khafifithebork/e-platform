# Frontend state, forms and API behaviour

**Status:** specification of implemented behaviour, plus acceptance criteria
**Last updated:** 2026-09-27
**Governed by:** ADR-004 (clients branch on problem type), ADR-024 (static public
catalogue), ADR-026 (the learner surface), ADR-031 (boundaries), CLAUDE.md
invariants 3, 5, 9, 12, 15, 16

Most of this **already works.** It is written down because an undocumented
convention is one refactor from being lost, and because two of these patterns
were got wrong first and fixed at a cost worth not paying twice.

Sections marked **GAP** describe behaviour that is missing or wrong today.

---

## 1. Where a piece of state lives

Five places. Choosing wrongly is the most common cause of a bug that cannot be
reproduced.

| Kind | Home | Examples |
|---|---|---|
| **Local UI** | `useState` in the component that owns the interaction | Drawer open, accordion expanded, the search box's text |
| **URL** | The route, or `useSearchParams` behind a Suspense boundary | A reset token. **Almost nothing else — see §2** |
| **Server data** | Fetched in a client component via `api.*`, held in that component's state | The current user, enrolments, a lesson, progress |
| **Form** | `useState` per field, plus a `fieldErrors` map from the API | Every form in `(auth)` |
| **Preferences** | Nowhere yet | See §9 |

**No global store, no data-fetching library, no form library.** Each would need
§5 approval and none has a demonstrated need: the deepest state in the product is
`LessonPlayer`, and it is one component. A second consumer of `/auth/me/` was
judged cheaper than a context provider — `useCurrentUser`'s docstring has the
reasoning, and that judgement is worth preserving rather than re-litigating.

---

## 2. URL state is deliberately almost unused

The obvious design puts catalogue filters in query parameters. **This product
must not**, and there is a guard.

Reading `searchParams` in a page under `(marketing)` opts that route out of static
generation, breaking invariant 15 and ADR-024. So `CourseCatalogue` holds filter
state in the component and filters a course list embedded at build time.
`(marketing)/courses/page.tsx` says so, and a guard looks for `searchParams` by
name in that route group so the obvious mistake fails rather than silently making
the catalogue dynamic.

**The cost is real and should be stated:** a filtered catalogue view is not
linkable, not bookmarkable, and lost on reload. That is a consequence of the
static decision, not an oversight.

`useSearchParams` appears **twice** — `reset-password` and, since 2026-09-28,
`verify-email` — both for an emailed token, both inside a `Suspense` boundary whose
fallback carries the `<h1>` so the prerendered document is not headingless. That
fallback *is* the whole static document for those routes, which is why it carries a
heading rather than the word "Loading".

**Neither page prefills the token into a field, and that is a security property
rather than an omission** — see ADR-034 §3. A token from `?token=` lives in state
and reaches only the API; the visible field appears only when the URL carried
nothing, because a prefilled input is the token in the DOM. Both pages assert it
against `innerHTML`, and both assert the seam — showing the field on the link path
fails a test.

Reading the token from the URL at all is a fallback, not the main path: **both auth
emails send a bare token with no URL**, so the paste field is what every real
redemption uses today. ADR-034 §2 records what sending links would cost.

**If shareable filtered URLs are ever wanted**, that is a change to ADR-024's
shape, not a frontend refactor. It needs an ADR.

---

## 3. The API client

`src/lib/api/client.ts` is the only place `fetch` is called. Every call goes
through `request()`, which:

1. Generates an `X-Request-ID` unless the caller supplied one, so a browser action
   and the Django and Celery work it caused can be joined in a log query.
2. Fetches `/auth/csrf/` first for any unsafe method when no cookie exists —
   login is deliberately not CSRF-exempt.
3. Sends `credentials: "same-origin"` so the session cookie rides along and never
   touches JavaScript (invariant 9).
4. Throws `ApiError` on any non-ok response, carrying the parsed problem document.
5. Returns `undefined` for 204.

**Types are generated** from the DRF OpenAPI schema into `src/types/api.d.ts`
(invariant 16). CI fails if they drift. A hand-written request or response type is
a bug — it drifts the first time the API changes, and the drift shows up at runtime
rather than as a build failure.

### Acceptance criteria

- No component calls `fetch` directly.
- No component declares an interface that mirrors an API payload.
- A test that stubs `fetch` must answer the CSRF probe separately from the
  request under test — `src/test/api.ts` exists because a single
  `mockResolvedValue` hands the probe the response meant for the form, and the
  failure reads as "the page ignored the error".

---

## 4. Reading a refusal: branch on type, echo the wording

ADR-004 is the authority. Two rules from it that the frontend must not break:

**Branch on `problem.type`, never on a status code or a message string.**
`ApiError` exposes `isNotAuthenticated` and `entitlementReason` for the two the
product cares about.

**Echo the API's wording; do not improve it.** `login/page.tsx` sets
`setProblem(error.problem.detail)` and its comment says why: the backend answers
identically for a wrong password, an unknown address and a locked account, so
substituting a friendlier message leaks the distinction the backend went to
trouble to hide. A test asserts two different `detail` strings both render, so a
hardcoded message fails.

**The one message the frontend may invent** is the transport failure — `fetch`
rejects, no problem document exists, and there is nothing to echo.

**And the one refusal it makes without asking:** an empty token on
`reset-password` and `verify-email`. The service layer short-circuits an empty
token — hashing the empty string produces a real digest, and a stored row must not
be matchable by sending nothing — so a POST with one is a certain failure that
spends a rate-limit slot and answers with a message about a token rather than about
the blank field. Both pages set a field error instead, and both provoke it. This is
the *only* case where the frontend decides a request will fail; everywhere else it
asks and echoes.

### Entitlement refusals

Invariant 3 and invariant 12: `resolve_access` returns a *reason*, the frontend
presents it, and **frontend visibility is never authorization.** The reason table
is `lib/entitlements/denial.ts`, typed `Record<DenialReason, Refusal>` against the
generated enum, so **a reason added by M8 or M9 without a message is a compile
error.** ADR-026 §3 explains why that mattered: the previous hand-written table
was keyed on two codes that had never existed while four real refusals had no
branch at all.

`GRACE_PERIOD_ENDED` has no action link on purpose — the useful destination is a
billing page, and there is none until M8.

---

## 5. Unknown is not loading, and a 403 is not an error

The pattern that was got wrong first, twice, and is now the house style.

```
AuthState = { status: "unknown" } | { status: "anonymous" } | { status: "signed-in", me }
```

- **Start from `unknown`.** Rendering signed-out as a placeholder flashes "Sign
  in" at every subscriber on every page load and reads as having been logged out.
- **A 403 from `/auth/me/` or `/me/courses/` is the answer "nobody".** Treating it
  as a failure leaves the header stuck for the majority of visitors to a public
  catalogue.

Four distinct states, and collapsing any two is a bug:

| State | Means | Renders |
|---|---|---|
| Unknown | Answer coming, guessing is harmful | Neither branch. Nothing |
| Loading | Answer coming, waiting is expected | `aria-live="polite"` text, not a bare spinner |
| Empty | Answer arrived, it is nothing | An explanation and a route onward |
| Error | Answer did not arrive | A refusal or a `Notice`, per §4 |

`CourseProgress` renders **nothing** in three of its four states, deliberately: it
is supplementary detail on a page complete without it, and an error strip on the
busiest page in the product would be worse than silence.

---

## 6. Cancellation and stale responses

Every fetching component uses the same shape:

```
useEffect(() => { let current = true; … if (!current) return; … return () => { current = false }; }, [deps])
```

This is not an abort — the request completes, its result is discarded. Adequate
because nothing here is expensive enough to be worth aborting, and it prevents the
real bug: a slow response for course A landing after the user has navigated to
course B. React Strict Mode runs effects twice in development, which this
tolerates.

**`LessonPlayer` uses refs, not state, for everything its ticker touches.** The
interval is installed once; reading state inside it would close over the first
render's values and report the same beat forever.

---

## 7. Retry safety and duplicate submissions

- **Every form disables its submit while pending** via `Button`'s `pending`, which
  also sets `aria-busy`. That is the duplicate-submission guard.
- **Progress beats are not retried.** `send()` clears the unreported counter
  *before* the request, because a beat that fails has still consumed that stretch
  of watching — carrying it forward would let a flaky connection accumulate an
  hour and claim it all at once. A dropped beat is not worth interrupting a lesson
  over; the next one carries the playhead.
- **An entitlement refusal mid-lesson is different from a dropped beat**: it means
  the subscription lapsed while watching, so the player pauses. Continuing would
  show paid content to somebody no longer paying.
- **The final beat uses `sendBeacon`**, because a normal fetch during unload is
  cancelled.
- **A single-use token is redeemed on a press, never in an effect.**
  `verify-email` could verify on mount and it deliberately does not: the token is
  consumed by the first POST, so a second one fails, and React's double-invoked
  development effects, a refresh and a back-navigation would each report "not
  valid" for a token that worked. ADR-034 §4. A test asserts nothing is posted
  before the press.

### An endpoint with no caller is not a wired endpoint

**Four auth endpoints had none.** `verify-email`, `resend-verification` and, in
effect, `password/reset/confirm/` — which only a URL nobody could receive would
reach — were wired on 2026-09-28. **`password/change/` followed on 2026-09-29**: the
only authenticated endpoint in the auth group, present since M2, and a signed-in
learner could change their password only by signing out and using the emailed reset.

`api.verifyEmail` had existed the whole time, which is the trap: a wrapper in
`client.ts` looks like coverage and proves only that somebody typed the URL.

Worth a check when a milestone claims a flow is done: grep the client's methods for
callers outside `client.ts`. A method with none is either dead or a flow that
cannot be completed.

**Match `api\s*\.\s*method`, not `api.method`.** A chained call puts the method on
its own line — `LessonGate` calls `api\n  .lessonBySlug(…)` — and the naive pattern
reports it as uncalled. Running it that way on 2026-09-28 found one genuinely
uncalled method, `api.lesson`, the by-id variant that `lessonBySlug` superseded at
M16 T3. Dead rather than broken, and **not removed**: deleting code on a hunch is
its own hazard, and it is recorded here instead.

---

## 8. Pagination — fixed 2026-09-27

`/me/courses/` is **cursor**-paginated: `next`, `previous`, `results`, and no
`count`. `MyCourses` read `page.results` and ignored the rest.

**The root cause was a type, not an oversight.** The client declared
`request<{ results: Enrollment[] }>` — a hand-written response shape, which
invariant 16 calls a bug — and because it omitted `next`, the second page was not
so much ignored as *invisible*. It now uses the generated
`PaginatedEnrollmentList`, so dropping a field is a deliberate act.

**A "load more" button, not page numbers.** A learner's own course list is a short
list they scan rather than a table they navigate, and cursor pagination gives no
total, so numbered pages could not say how many there are even if they were wanted.

### `next` must not be followed, and this is the part to remember

Django builds that URL from the request's Host header. **We sit behind the Next.js
rewrite, which forwards its own destination as Host** — the same fact `base.py`
records as the reason `CSRF_TRUSTED_ORIGINS` is required. So `next` names `api` or
the internal hostname, never the origin the browser is on.

A component following it verbatim would request the wrong host from the browser,
and in production would be an attempt on an internal name. `cursorFrom` extracts
the `cursor` parameter and discards the origin; the fixtures in
`MyCourses.test.tsx` deliberately carry `http://api/...` so that a regression here
fails rather than passing on a convenient localhost URL.

**Any future paginated endpoint has the same constraint.** This is the first one
the frontend consumes, so the rule is written here rather than in that one
component.

### Acceptance criteria

- The control appears only when the API reported a next page.
- A page appends; it does not replace.
- **A failed "load more" keeps what is already on screen**, with the cursor
  retained so retrying is one click. Moving to the failed state would replace a
  usable list with an error, which is worse than the error alone.
- A malformed `next` ends the list rather than throwing.

All four provoked. Five assertions in `MyCourses.test.tsx`.

## 9. Preferences — **GAP, and constrained**

There is no preferences mechanism, and two things constrain adding one:

- **Invariant 9.** Nothing auth-related in `localStorage` or `sessionStorage`,
  ever. A theme or a "transcript panel collapsed" flag is not auth-related and is
  permitted; a user id, an email, a token or an entitlement decision is not.
- **No endpoint.** Anything in browser storage is per-device and will disagree
  with the same person's other device.

ADR-032 declines a theme toggle partly on these grounds. If a preference is ever
added, it is per-device, non-sensitive, and wrapped in `try`/`catch` — storage
throws in private windows and with site data blocked.

---

## 10. Cache invalidation and session changes

There is no cache, which makes this short and is a feature.

- **After a mutation**, the component holds the response as its new state.
  `recordProgress` returns the updated progress and `LessonPlayer` stores it,
  rather than refetching.
- **Login** does a `router.push("/")`, remounting the tree, so every
  `useCurrentUser` resolves afresh. No cache to invalidate.
- **Logout** must leave nothing behind. Since nothing personal is ever written to
  storage (invariant 9, asserted by tests in `AuthMenu.test.tsx` and
  `login/page.test.tsx`), there is nothing to clear — **which is the point of that
  invariant**, not a happy accident.
- **Session expiry mid-session** surfaces as `ApiError` with
  `isNotAuthenticated`, or as `LOGIN_REQUIRED` from the entitlement resolver on a
  gated read. The refusal table handles the latter. **GAP:** there is no
  application-wide response to the former — each component decides, and a learner
  whose session expires between page loads finds out at their next action rather
  than being told.

### Acceptance criteria

- A test asserting `localStorage.length === 0` and `sessionStorage.length === 0`
  after a successful login. Exists.
- No component writes to storage. Enforced by review; the invariant is the rule.

---

## 11. Measured baseline, per route

**Re-measured 2026-09-30**, after seven batches of the quality addendum added two
routes and roughly eight components. The 2026-09-28 figures are kept beside the new
ones, because the delta is the useful number and a replaced table loses it.
**Nothing here is enforced**; see the note on a budget below.

| Route | JS chunks | JS gz | CSS gz | **Total gz** | vs 2026-09-28 |
|---|---|---|---|---|---|
| `/` | 15 | 321,223 | 6,061 | **327,284** | +1,270 |
| `/account` | 16 | 320,036 | 6,061 | **326,097** | *new* |
| `/my-courses` | 16 | 319,855 | 6,061 | **325,916** | +1,382 |
| `/courses` | 15 | 318,698 | 6,061 | **324,759** | +1,593 |
| `/courses/[slug]` | 15 | 317,496 | 6,061 | **323,557** | +1,269 |
| `/pricing` | 15 | 315,871 | 6,061 | **321,932** | +1,276 |
| `/verify-email` | 15 | 312,660 | 6,061 | **318,721** | *new* |
| `/reset-password` | 15 | 312,494 | 6,061 | **318,555** | +1,246 |
| `/register` | 15 | 312,335 | 6,061 | **318,396** | +1,241 |
| `/forgot-password` | 15 | 312,279 | 6,061 | **318,340** | +1,252 |
| `/login` | 15 | 312,217 | 6,061 | **318,278** | +1,212 |
| `/_not-found` | 13 | 307,619 | 6,061 | **313,680** | +1,189 |
| `_global-error` | 8 | 250,704 | 0 | **250,704** | +763 |

### What the delta says, and what it rules out

**Every route grew by 1.2–1.6 KB, and the uniformity is the finding.** `_global-error`
imports none of the seven batches' components and still grew 763 bytes, so this is not
per-page code — it is shared modules getting bigger. `lib/api/client.ts` alone gained
three methods (`changePassword`, `resendVerification`, `verifyEmail`'s first caller
pulling it in) and is imported almost everywhere, `global-error` included.

**It is not a dependency bump, and that was checked rather than assumed.** No runtime
package moved: the last lockfile change touching one was `1b4c0d1`, which *is* the
baseline commit. 2026-09-30's lockfile work — `wrangler`, `undici`, `brace-expansion`
— is dev and build-time only.

**CSS grew 82 bytes**, 5,979 → 6,061, which is the `::cue` rule from batch four.

**Seven batches cost about 0.4%.** Two new routes, an account surface, a share-card
module, a retry component used by four surfaces, playback preferences, a skill filter
and three generated images, for roughly 1.3 KB gz on a cold visit. The attribution to
shared modules is inference from the shape of the numbers rather than a bundle
analysis; the dependency fact above is measured.

**How measured.** `rm -rf .next && npm run build`, then for each prerendered page
under `.next/server/app/**/*.html`, the unique `<script src>` and stylesheet
references were resolved to files and gzipped at level 9. That is what a browser
downloads for a cold visit to that route, not an estimate. The 2026-09-30 figures
reproduce that method exactly, which is the only reason the deltas mean anything —
a different method would have produced a different number and looked like a change.

**Next 16 with Turbopack emits no `app-build-manifest.json`**, and its build output
no longer prints a size table, so the served HTML is the honest source. An earlier
version of this section reported 357 KB as "all chunks, an upper bound"; the real
per-route figures are 312–326 KB, so that proxy was close but it was a proxy.

### Two things the table says

**The routes are nearly identical — a 14 KB spread across ten of them**, and still
nearly identical after seven batches: 13.6 KB across twelve. Almost everything is
shared baseline rather than per-page code, so route-level splitting has little left to
give. Any meaningful reduction has to come out of the shared chunks — which is also
why the growth landed on every route at once.

**`_global-error` is 76 KB lighter and loads 8 chunks instead of 15, with no CSS at
all.** That is ADR-031's design intent showing up in a measurement rather than a
docstring: the last-resort boundary was written to depend on nothing, and it
measurably does not. `boundaries.test.tsx` asserts the same property from the
source side. It held through seven batches — still 8 chunks, and the only route whose
growth is under a kilobyte.

### The lesson route is not in the table

It is the only dynamic route (ADR-026), so it has no prerendered HTML to read. Its
first load has to be measured in a browser's network panel — which makes it a
person's job, and it is the route most worth doing, because it is the one a learner
waits on.

### The budget is a gate — **approved and enforced 2026-10-03**

A ceiling of **350 KB gzipped per route** sits about 7% above the worst route
(`/` at 327 KB), which is enough headroom for ordinary work and tight enough to catch
a dependency arriving unnoticed. **Seven batches moved the worst route by 1.3 KB**, so
7% is a great deal of room — the gate catches a dependency, not ordinary feature work,
which is what it is for.

**Enforced since 2026-10-03** by `scripts/assert-bundle-budget.mjs`, wired as
`npm run verify:bundle` and run in CI beside `verify:static`, `verify:a11y` and
`verify:css`. It reproduces the method above exactly — that is the whole point, since
a different method would produce a different number and read as a regression on the
first run — and it agrees with the 2026-09-30 figures to within 120 bytes.

**Those 120 bytes are the Next 16.3.3 → 16.3.8 patch**, and the attribution is
checkable rather than assumed: that security bump is the only change to the client
bundle between the two measurements, because everything shipped in between is a build
script, a test, or a server component.

Three floors keep it honest, all provoked: a route over the ceiling fails; a page
whose assets cannot be resolved at all fails, because a page that weighs zero would
otherwise pass every budget; and an empty page list fails rather than reporting
success over nothing.

**It does not cover the lesson route**, which is dynamic (ADR-026) and has no
prerendered HTML — and that is the route a learner actually waits on. Still a person's
job with a network panel, and the gate passing must not be read as covering it. Enforcing it needs the owner (roadmap E4),
and it should be a script beside `verify:static` and `verify:css` rather than a
number in a document nobody runs.

**The first lever, if it ever bites.** The largest single chunk on every route is
75 KB gzipped and contains the **Sentry SDK** alongside Next internals — its exact
share is not separable without a bundle analyser, which is a §5 dependency nobody
has approved. Worth stating plainly: **that SDK ships on every page and has never
sent an event**, because no DSN is configured in this repository (ADR-027 §3). That
is not an argument for removing it — a DSN will exist — but it is where to look
first, and lazy-loading it is a real option ADR-027 did not consider.

## 11a. Cookies and browser storage — a complete inventory

**Written down because §3 of the quality addendum asks for it, and because the
answer decides whether this product needs a consent banner.** Verified against
settings and source on 2026-09-30, not assumed.

| Stored | Where | Set by | Purpose | Class |
|---|---|---|---|---|
| `sessionid` | cookie, `HttpOnly`, `SameSite=Lax`, `Secure` in production | Django | Authentication. The session itself lives in Postgres (`SESSION_ENGINE = ...backends.db`) — the cookie is an opaque key | Strictly necessary |
| `csrftoken` | cookie, `SameSite=Lax`, `Secure` in production | Django | CSRF defence. Readable by script on purpose: `client.ts` reads it to set `X-CSRFToken`, which is how the double-submit check works | Strictly necessary |
| `lingua.playbackRate` | `localStorage` | the player (batch four) | Remembers a playback speed between 0.5 and 1.5 | Functional, set only by a deliberate user action |

**That is the whole list.** There is no analytics, no tag manager, no embedded
player, no font CDN, no social widget, and **no third-party script of any kind** —
grepped for `<Script`, `gtag`, `analytics` and `plausible`, and the compiled output
loads nothing off-origin.

### What follows from it

**No consent banner is required today, and adding one would be worse than not.** The
two cookies are strictly necessary for a service the user asked for, which is the
exemption every EU implementation of the ePrivacy rule provides. The one
`localStorage` entry is a preference the user sets by operating a control, stores a
number, and reveals nothing. A banner asking permission for that would train people
to dismiss a dialogue that protects nothing — the quality addendum's own instruction
is not to add one "purely for appearance", and this is the evidence behind that call.

**What would change it**, and this is the useful half of writing it down:

- **A video provider.** Mux, Cloudflare Stream and YouTube all set storage of their
  own, and an embedded player is the single most likely source of a non-essential
  cookie in this product. §11 #1's sibling decision. **Re-run this inventory the day
  a provider is chosen.**
- **Any analytics**, including self-hosted.
- **Sentry session replay.** The SDK ships on every page and has never sent an event
  (no DSN, ADR-027 §3), and replay is not enabled. Enabling it would collect
  interaction data and needs its own assessment.

**This inventory is not a privacy policy and does not substitute for one.** It is the
factual input a policy needs — §1's policy pages remain blocked on owner-supplied
content, and a policy asserting this list is accurate is a claim about business
practice that only the operator can make.

### Nothing auth-related is in browser storage

Invariant 9, and it is asserted rather than trusted: `reset-password`,
`verify-email` and `ChangePassword` each check that no token or password reaches
`localStorage` or `sessionStorage`. `preferences.ts` is the only production writer,
and it writes one number under a namespaced key.

---

## 12. Open items

| Item | Section | Status |
|---|---|---|
| ~~Pagination on `/me/courses/`~~ | §8 | **Fixed 2026-09-27** |
| App-wide session-expiry response | §10 | Implemented 2026-10-17; ADR-038, commits `6c5099e` / `d105061` |
| Performance budget | §11 | Enforced at 350 KB per static route; dynamic lesson measured separately in STATUS |
| No preferences mechanism | §9 | Not needed yet |
| Filtered catalogue URLs are not shareable | §2 | Consequence of ADR-024, not a bug |
