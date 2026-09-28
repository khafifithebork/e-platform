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

**Three auth endpoints had none until 2026-09-28** — `verify-email`,
`resend-verification`, and in effect `password/reset/confirm/`, which only a URL
nobody could receive would reach. `api.verifyEmail` had existed the whole time,
which is the trap: a wrapper in `client.ts` looks like coverage and proves only
that somebody typed the URL.

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

Measured 2026-09-28 from a production build. **Nothing here is enforced**; see the
note on a budget below.

| Route | JS chunks | JS gz | CSS gz | **Total gz** |
|---|---|---|---|---|
| `/` | 14 | 320,035 | 5,979 | **326,014** |
| `/my-courses` | 15 | 318,555 | 5,979 | **324,534** |
| `/courses` | 14 | 317,187 | 5,979 | **323,166** |
| `/courses/[slug]` | 14 | 316,309 | 5,979 | **322,288** |
| `/pricing` | 14 | 314,677 | 5,979 | **320,656** |
| `/reset-password` | 14 | 311,330 | 5,979 | **317,309** |
| `/register` | 14 | 311,176 | 5,979 | **317,155** |
| `/forgot-password` | 14 | 311,109 | 5,979 | **317,088** |
| `/login` | 14 | 311,087 | 5,979 | **317,066** |
| `/_not-found` | 12 | 306,512 | 5,979 | **312,491** |
| `_global-error` | 8 | 249,941 | 0 | **249,941** |

**How measured.** `rm -rf .next && npm run build`, then for each prerendered page
under `.next/server/app/**/*.html`, the unique `<script src>` and stylesheet
references were resolved to files and gzipped at level 9. That is what a browser
downloads for a cold visit to that route, not an estimate.

**Next 16 with Turbopack emits no `app-build-manifest.json`**, and its build output
no longer prints a size table, so the served HTML is the honest source. An earlier
version of this section reported 357 KB as "all chunks, an upper bound"; the real
per-route figures are 312–326 KB, so that proxy was close but it was a proxy.

### Two things the table says

**The routes are nearly identical — a 14 KB spread across ten of them.** Almost
everything is shared baseline rather than per-page code, so route-level splitting
has little left to give. Any meaningful reduction has to come out of the shared
chunks.

**`_global-error` is 76 KB lighter and loads 8 chunks instead of 14, with no CSS at
all.** That is ADR-031's design intent showing up in a measurement rather than a
docstring: the last-resort boundary was written to depend on nothing, and it
measurably does not. `boundaries.test.tsx` asserts the same property from the
source side.

### The lesson route is not in the table

It is the only dynamic route (ADR-026), so it has no prerendered HTML to read. Its
first load has to be measured in a browser's network panel — which makes it a
person's job, and it is the route most worth doing, because it is the one a learner
waits on.

### No budget is proposed as a gate — but here is the shape of one

A ceiling of **350 KB gzipped per route** would sit about 7% above today's worst
(`/` at 326 KB), which is enough headroom for ordinary work and tight enough to
catch a dependency arriving unnoticed. Enforcing it needs the owner (roadmap E4),
and it should be a script beside `verify:static` and `verify:css` rather than a
number in a document nobody runs.

**The first lever, if it ever bites.** The largest single chunk on every route is
75 KB gzipped and contains the **Sentry SDK** alongside Next internals — its exact
share is not separable without a bundle analyser, which is a §5 dependency nobody
has approved. Worth stating plainly: **that SDK ships on every page and has never
sent an event**, because no DSN is configured in this repository (ADR-027 §3). That
is not an argument for removing it — a DSN will exist — but it is where to look
first, and lazy-loading it is a real option ADR-027 did not consider.

## 12. Open items

| Item | Section | Status |
|---|---|---|
| ~~Pagination on `/me/courses/`~~ | §8 | **Fixed 2026-09-27** |
| No app-wide session-expiry response | §10 | Gap, needs a decision on what the app should do |
| No performance budget | §11 | Needs per-route figures first |
| No preferences mechanism | §9 | Not needed yet |
| Filtered catalogue URLs are not shareable | §2 | Consequence of ADR-024, not a bug |
