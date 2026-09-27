# ADR-031 — Error and loading boundaries, and the report nobody receives

**Status:** proposed
**Date:** 2026-09-27
**Decides:** where App Router boundaries go, what they say, and how a client
render error reaches Sentry
**Depends on:** ADR-004 (clients branch on problem type), ADR-024 (the public
catalogue stays static), ADR-026 (the learner surface), ADR-027 (error reporting)

---

## Decision

**Three files, and one of them is the whole point:**

| File | Scope |
|---|---|
| `src/app/global-error.tsx` | The last resort. Replaces the document, so it carries its own `<html>` and `<body>` and cannot use the shell |
| `src/app/(learner)/error.tsx` | The authenticated surface, including the only dynamic route in the product |
| `src/app/(learner)/courses/[slug]/lessons/[lessonSlug]/loading.tsx` | The one route that genuinely waits on the network before it can render |

**And every boundary reports to Sentry**, which is the part that does not exist
today at all.

No `error.tsx` for `(marketing)` or `(auth)`. Reasoning in §3 — a boundary on a
statically generated page catches almost nothing and costs a client component at
the root of a route group that invariant 15 keeps static.

---

## 1. What happens today

**There is no `error.tsx`, `loading.tsx` or `global-error.tsx` anywhere in
`src/app`.** Verified against the tree, not assumed.

So a render-time exception in a client component — and the learner surface is
client components almost entirely, by ADR-026 decision 2 — produces Next.js's
built-in error page. In production that is an unstyled screen reading
"Application error: a client-side exception has occurred". No shell, no
navigation, no skip link, no way back except the browser's own controls.

**The learner in the worst position is the one who was mid-lesson.** ADR-026
records that `LessonPlayer` reports progress on an interval and a final beat on
unmount. A render error takes the component down; what the beat had not yet sent
is gone, and the page that replaces it does not say so.

### The part that matters more

**ADR-027 configured Sentry for the browser, and a render error does not reach
it.** The SDK's automatic instrumentation catches unhandled window errors and
promise rejections; a React render error is *caught by React* and rethrown into
whatever error boundary exists. With no boundary, Next's own handler takes it.
Whether that forwards to Sentry depends on the framework's internals rather than
on anything this repository states — and an error reporter whose coverage is
"whatever the framework happens to do" is the situation ADR-027 §1 set out to
end.

An `error.tsx` receives the error as a prop. That is the documented place to call
`captureException`, and it is the only way this project can say what it reports.

---

## 2. Three boundaries, and why not more

**`global-error.tsx`** catches failures in the root layout itself. It must render
`<html>` and `<body>` because it replaces the document, which also means it
cannot use `SiteShell` or the tokens applied to `body`. Keep it deliberately
plain: a heading, a sentence, a link to `/`, and a `captureException`. A
last-resort page that needs the design system to work is a last-resort page that
fails when the design system is the thing that broke.

**`(learner)/error.tsx`** is the useful one. It wraps `/my-courses` and the lesson
route, both authenticated, both client-rendered, and one of them dynamic. It gets
`reset()` and can offer a retry that re-renders the segment without a full
navigation — appropriate here, because the common cause is a failed request
rather than a broken build.

**`(learner)/.../loading.tsx`** exists because the lesson route is the only place
where the shell can be painted before the content is known. ADR-026: it is the
only dynamic route in the product. Everything else is prerendered, so a
`loading.tsx` would flash for a frame or not appear at all.

### Not adding

- **`(marketing)/error.tsx`.** These pages are built from data fetched at build
  time (ADR-024). By the time a browser has the HTML, the fetch already
  succeeded. What remains is hydration failure — which `global-error` catches —
  and the two personalised client components, which ADR-026 designed to fail
  silently by rendering nothing. A boundary here would mostly catch nothing, and
  `error.tsx` is necessarily a client component at a route-group root that
  invariant 15 requires to stay static. Not worth the risk for the coverage.
- **`(auth)/error.tsx`.** Every page in the group already handles its own failure
  states: `ApiError` becomes a `Notice`, field errors go to the `Field`, and a
  transport failure gets the one message the pages are allowed to invent. Those
  are tested. A boundary would sit above working error handling.
- **`not-found.tsx` beyond the two that exist.** Already covered.

---

## 3. What the boundaries are allowed to say

ADR-004 has the rule this follows: clients branch on `problem.type`, and the
frontend presents the backend's wording rather than inventing its own. That rule
was written for API refusals and it applies here too, in a specific way.

**A render error has no problem document.** Nothing arrived from the API; the
component broke. So a boundary is one of the few places the frontend legitimately
writes its own copy — the same licence `login/page.tsx` has for "Could not reach
the server", and for the same reason: there is no answer to echo.

Three rules:

1. **Never render the error's message or stack.** A message can carry a URL, an
   id, or a fragment of a response. `src/lib/observability/redact.ts` exists
   because ADR-027 took that seriously on the reporting path; the visible page
   must not undo it.
2. **Say what is lost.** On the lesson boundary, say that recent progress may not
   have been saved. It may not have been. A page that implies everything is fine
   is worse than one that admits it does not know.
3. **Offer the two useful destinations**, not a generic apology: retry via
   `reset()`, and a link out to `/my-courses` — an authenticated destination,
   since a learner hitting this is signed in.

---

## 4. Loading and empty states are not the same thing

Worth recording because the repository already distinguishes them correctly and
an undocumented convention is one refactor from being lost.

- **Loading** — the answer is coming. Every such state in the repo uses
  `aria-live="polite"` with text, not a bare spinner: `MyCourses` says "Loading
  your courses…", `LessonGate` says "Loading the lesson…". ADR-026 explains why —
  the rest of the page is empty while it resolves, so a screen-reader user
  otherwise gets no signal at all.
- **Unknown** — the answer is coming and *guessing is harmful*. The three-state
  auth pattern (`unknown | anonymous | signed-in`). ADR-026 decision 2: rendering
  signed-out as a placeholder flashes "Sign in" at every subscriber on every page
  load. **This is not a loading state and must not be collapsed into one.**
- **Empty** — the answer arrived and is nothing. `MyCourses` renders an
  explanation and a route onward, because enrolment happens by starting a lesson
  and there is nothing else to press.
- **Error** — the answer did not arrive. Distinguished from empty everywhere
  already; a 403 from `/auth/me/` or `/me/courses/` is an *answer*, not an error,
  per ADR-026.

`docs/specs/frontend-state-and-api.md` carries these as acceptance criteria.

---

## Consequences

**Positive.** A learner who hits a render error gets a page that says what
happened and how to get out. The project can state what it reports to Sentry
rather than inheriting whatever the framework does. Small: three files, no
dependency, no bundle of consequence.

**Negative.** `global-error.tsx` cannot use the design system, so there is one
page whose styling is maintained separately and will drift — accepted, because
the alternative is a fallback that depends on the thing that failed. Boundaries
also make some failures *less* visible in development, where a red overlay is
more useful than a friendly page; anyone debugging should know they are there.

**UX and responsive.** All three are text and links, so they reflow at 320px
without special handling. The lesson `loading.tsx` should reserve the player's
space rather than collapse it, or the page will shift when content arrives —
which is a layout-stability concern, and the one performance-adjacent line in
this ADR.

**Accessibility.** Each boundary is a page: one `<h1>`, real headings, a focusable
link. `verify:a11y` reads built HTML and will not see these — they render only on
failure — so they need component tests instead, the same gap ADR-026 records for
the dynamic lesson route. The retry control is a `<button>`, never a styled
`<div>`.

**Security.** §1 of the three rules is the security-relevant one: no error text
to the DOM. Also no error detail in a URL, ever — that is the privacy rule
`redact.ts` enforces on the way out.

---

## Implementation guidance

- `error.tsx` and `global-error.tsx` are Client Components by definition; mark
  them `"use client"`.
- Call `captureException` in an effect, not in the render body, so a
  double-render cannot double-report.
- Reuse `PageTitle` with `variant="interstitial"` on `(learner)/error.tsx` — a
  refusal-shaped page, which is what that variant is for
  (`docs/design-system.md`). `global-error.tsx` cannot, and writes its own.
- Do not add a retry counter or backoff. A person pressing a button twice is not
  a retry storm, and `reset()` is idempotent.

## Verification criteria

1. A test per boundary that renders it with a thrown error and asserts: one
   `<h1>`, the error's own message absent from the DOM, and `captureException`
   called once.
2. Each provoked — remove the `captureException` call and the assertion must
   fail; render the message and the redaction assertion must fail.
3. The lesson `loading.tsx` asserts an `aria-live` region with text, matching the
   convention in §4.
4. `verify:static` still reports four prerendered public routes after the files
   land, confirming no boundary pulled a static route dynamic.

## Related

ADR-004, ADR-024, ADR-026, ADR-027, ADR-030 (an error page is an accessibility
surface). `docs/specs/frontend-state-and-api.md` for the state taxonomy.

**Approval required:** the owner. No dependency, no service, no cost — three
files and a reporting call.
