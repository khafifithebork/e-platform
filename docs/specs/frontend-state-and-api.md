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

`useSearchParams` appears exactly once — `reset-password`, for the emailed token,
inside a `Suspense` boundary whose fallback carries the `<h1>` so the prerendered
document is not headingless.

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

---

## 8. Pagination — **GAP**

`/me/courses/` returns a paginated envelope. `MyCourses` reads `page.results` and
**ignores every other field.**

A learner with more enrolments than one page sees the first page and no
indication that more exist. No control, no count, no "load more". It fails
silently, which is the worst version.

Not urgent — no real learner has enough enrolments yet — but it is a defect and
not a decision. Whoever fixes it should decide between a "load more" button and
paging, and prefer the button: a learner's own course list is a short list they
scan, not a table they navigate.

`CourseCatalogue` is unaffected. It filters a build-time list and shows a live
result count.

---

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

## 11. Measured baseline

Numbers below were **measured** on 2026-09-27 from a production build, not
estimated. Nothing here is a budget; see the note.

| Metric | Measured |
|---|---|
| Client JS, all chunks, uncompressed | 1,099,885 bytes across 23 files |
| CSS, uncompressed | 26,810 bytes, 1 file |
| **JS + CSS, gzipped** | **357,089 bytes (349 KiB)** |
| Largest single chunk, uncompressed | 465,065 bytes |
| Public routes prerendered | 4 (`/`, `/courses`, `/courses/[slug]`, `/pricing`) |
| Dynamic routes | 1 (the lesson page) |

**How measured:** `rm -rf .next && npm run build`, then summing
`.next/static/chunks/**/*.{js,css}` and gzipping each at level 9.

**Read this carefully: it is a total across all chunks, not a per-route first
load.** No route loads all 23 files. It is an upper bound, and the framework's own
per-route table would be the right source for a real budget — Next 16 no longer
prints sizes in the build output used here, so that was not available.

**No budget is proposed.** A threshold invented without knowing the per-route
split would either never fire or fire constantly, and a guard that fires
constantly gets deleted. The honest next step is to obtain per-route first-load
figures and *then* propose a ceiling — most usefully on the lesson route, which is
the only dynamic one and the one a learner waits on.

---

## 12. Open items

| Item | Section | Status |
|---|---|---|
| Pagination on `/me/courses/` | §8 | Defect, unscheduled |
| No app-wide session-expiry response | §10 | Gap, needs a decision on what the app should do |
| No performance budget | §11 | Needs per-route figures first |
| No preferences mechanism | §9 | Not needed yet |
| Filtered catalogue URLs are not shareable | §2 | Consequence of ADR-024, not a bug |
