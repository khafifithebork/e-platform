# Frontend roadmap — the remaining gaps, in dependency order

**Status:** written 2026-09-27 and **substantially overtaken the same day.**
**Depends on:** nothing outstanding — **all four ADRs were accepted by the owner on
2026-09-27**, and two of the four defects were fixed in the process.

| ADR | Status | Left to do |
|---|---|---|
| ADR-030 — WCAG 2.2 AA | **accepted** | **nothing.** C3, all of C4 and D2 are done; 2.4.11 was found, reproduced and fixed |
| ADR-031 — boundaries | **accepted** | **nothing.** D1 built 2026-09-28 |
| ADR-032 — theme, toggle declined | **accepted** | nothing. §2's defect fixed; A4 still confirms it |
| ADR-033 — localisation deferred | **accepted** | §3's `<track>` gap, blocked on backend (D4) |

**Five of six defects are fixed** — `color-scheme` declared, inline-direction
utilities logical with a pinned guard, error and loading boundaries built (D1),
`/me/courses/` pagination (D3), and **2.4.11 Focus Not Obscured**, which the owner
found with a keyboard and which was then reproduced, measured and fixed. The sixth,
`<track>`'s language attributes, is **blocked on backend modelling** rather than
open.

**Nothing is left behind an accepted ADR.** C3, all three of C4's tests and D2 all
landed; the 2.4.11 failure — the only real WCAG 2.2 gap in the product — was
reported by the owner, reproduced, measured and fixed on 2026-09-28.

**Section A stands at three and a half down.** A1 confirmed in full and **A5
measured**; A2's 2.4.11 check and A3's focus-ring check both done, with the remainder
of each still open. **A4 is untouched**, as is the lesson route's first load.

**Accepted still does not mean implemented.** Acceptance settles the decision so
the work may be planned; it does not skip CLAUDE.md §7.

**This does not change the milestone plan.** `docs/STATUS.md` holds current state
and `CLAUDE.md` §10 holds milestone order; M14 stands at 6 of 10 and nothing here
jumps ahead of it. This is the frontend redesign workstream's tail, not a new
milestone, and **no item here is a second visual redesign** — the visual work
finished at stage 4.

Read the four categories as a sequence. **A is free and informs everything after
it**, so doing A last would be the expensive order.

---

## A — Verification of behaviour that already ships

**No code changes. Nothing here needs an ADR approved.** Each item converts a
believed claim into a known one, and two of them gate later work.

### A1 · Reduced motion in a real browser — **done 2026-09-28**

- **Benefit:** confirms the landing page is not blank for visitors who asked for
  less motion. Until stage 2 it was — entirely, for exactly those people.
- **Scope:** ten minutes. `docs/runbooks/accessibility-verification.md` §3.1.
- **Done 2026-09-28**, in two passes because the page uses two mechanisms. The owner
  confirmed in Firefox that the **headline** shows (proving the hydration fix — the
  mismatch is what left `opacity: 0` stuck inline) and, on scrolling, that the
  **featured course cards and all four panels** show (the `Reveal`/`StaggerList`
  path, driven by `whileInView` and an `IntersectionObserver`). Runbook §6 has both
  rows.
- **Re-check after any change to `MotionProvider`, `Reveal` or `StaggerList`.** No
  automated check can stand in: the agent's browser freezes
  `requestAnimationFrame`, so it cannot tell a working page from a broken one.
- **Approval:** none. It needed a person with a browser, and got one.

### A2 · Keyboard pass — **2.4.11 done 2026-09-28; the rest of the pass is not**

- **Done 2026-09-28:** the owner found the 2.4.11 fault — the focus ring behind the
  fixed "Site map" button. It was then reproduced and measured (420×480 on
  `/courses`, three overlapping elements) and fixed. **That unblocked and completed
  both C4's third test and D2.**
- **Still open:** the rest of §3.2 — focus visible at every stop across nine routes,
  the drawer's trap and restoration, the player's controls, the transcript's cues.
  A criterion that turned up one fault is worth finishing.
- **Approval:** none.

### A3 · Forced colours — **focus ring confirmed 2026-09-28; two checks open**

- **Done 2026-09-28:** the owner confirmed the focus ring is still visible in forced
  colours. That is the check worth having, because it guards a real earlier fix —
  Tailwind 4's `outline-none` silently dropped the transparent-outline fallback a
  high-contrast mode turns visible, and `outline-hidden` restored it. **The difference
  between the two is invisible outside such a mode**, so no automated check could ever
  have shown it.
- **Still open:** whether `Notice` stays distinguishable by its symbol, and whether
  the navigation's current-page state survives. Neither is likely broken — the symbol
  and `aria-current` are both in the markup — but neither has been looked at.
- **Approval:** none.

### A4 · Dark-mode browser furniture

- **Benefit:** confirms or refutes ADR-032 §2, which is **reasoning, not an
  observation** — deliberately labelled as such.
- **Scope:** look at the transcript panel's scrollbar and an autofilled login
  field in dark mode.
- **Acceptance:** a note in ADR-032's verification section saying what was seen.
- **No longer gates C1** — C1 shipped first, on the specification. A4 is now the
  confirmation that it did what it was meant to. **Measurement already corrected
  part of ADR-032 §2**: form-control boxes are unaffected, because Tailwind's
  Preflight resets them, so what is left to look at is scrollbars and autofill.
- **Approval:** none.

### A5 · Per-route first-load JS — **done 2026-09-28**

- **Done 2026-09-28.** Measured from the prerendered HTML — Next 16 with Turbopack
  emits no `app-build-manifest.json` and no size table, so the served `<script>`
  references are the honest source. Table in `frontend-state-and-api.md` §11.
- **Result: 312–326 KB gzipped, and the routes are nearly identical** — a 14 KB
  spread across ten of them. Almost everything is shared baseline, so route-level
  splitting has little left to give; any real reduction comes out of the shared
  chunks.
- **Two findings.** `_global-error` is 76 KB lighter with 8 chunks and no CSS, which
  is ADR-031's "depends on nothing" intent showing up as a measurement. And the
  largest chunk on every route — 75 KB gz — contains the **Sentry SDK**, which
  **has never sent an event** because no DSN is configured. That is where to look
  first if a budget ever bites, and lazy-loading it is an option ADR-027 did not
  consider.
- **Still open:** the **lesson route is not in the table.** It is the only dynamic
  route, so it has no prerendered HTML — its first load needs a browser's network
  panel, and it is the route most worth measuring because it is the one a learner
  waits on.
- **Approval:** none was needed to measure. A budget that gates CI still needs the
  owner — see E4.

---

## B — Documentation only

### B1 · Decide the four proposed ADRs — **done 2026-09-27**

All four accepted. ADR-030 (WCAG 2.2 AA) and ADR-031 (boundaries) first; then
ADR-032 declining the theme toggle and ADR-033 deferring localisation.

**Both of the latter two were split before being decided**, on the owner's
instruction and on one principle worth keeping: **a defect with no product question
attached should not wait behind one that has.** ADR-032 §2 (`color-scheme`) and
ADR-033 §2 (logical properties) shipped hours before the decisions they were
sitting behind. Worth reaching for again — the pattern is a file that mixes "this
is broken" with "what should we do", and the first half never needed the meeting.

### B2 · Resolve the architecture.md §8.2 discrepancy — **done 2026-09-28**

- **Done 2026-09-28.** The owner approved **`axe-core`** under §5; `MSW` and
  `Playwright` declined for now. architecture.md §8.2 is revised with the reasoning
  and ADR-030 §5 no longer reads as blocked, so the document and `package.json`
  agree.
- **`axe-core`, not `@axe-core/react`** — the latter logs to the console in
  development and fails nothing. Zero dependencies, and **verified absent from the
  client bundle.**
- **It found a real bug on the first run:** `Field` had `role="alert"` on its `<ul>`
  of error messages, which replaces the list's own role and orphans its `<li>`
  children. `Field.test.tsx` passed before *and* after the fix — it asserted an alert
  exists and contains the message, true either way. That is the class of fault the
  structural greps structurally cannot see, and the argument for the dependency.
- **Playwright worth revisiting at M8**, when there is a checkout to walk end to end.

---

## C — Small fixes, each behind an ADR

All small. Each needs its ADR accepted first, and each needs a provoked guard
(ADR-006) before it is believed.

| # | Fix | Waits on | Size |
|---|---|---|---|
| ~~**C1**~~ | ~~Declare `color-scheme` on `:root`~~ | **Done 2026-09-27** — split out of ADR-032 by the owner | shipped with 5 provoked tests |
| ~~**C2**~~ | ~~Four physical→logical utility swaps~~ | **Done 2026-09-27** — six, not four; split out of ADR-033 | shipped with a pinned guard |
| ~~**C3**~~ | ~~`contrast.test.ts` cites 2.2 AA~~ | **Done 2026-09-27** | no new arithmetic — 2.2 changes no contrast threshold |
| ~~**C4**~~ | ~~`autoComplete` (3.3.8)~~, ~~button minimum heights (2.5.8)~~, ~~the 2.4.11 remedy~~ | **All three done** — the first two 2026-09-27, the third 2026-09-28 | 17 assertions, all provoked |

**C1 is done.** `contrast.test.ts` still passes both schemes and `theme.test.ts`
pins the declaration. **A4 is still outstanding** and is now the only unverified
part: nobody has looked at a dark-mode scrollbar or an autofilled field, neither
being observable in the agent's browser.

**C2 is done.** Six swaps, not the four estimated, plus two navigation-chrome sites
pinned as a layout decision ADR-029 owns. LTR rendering confirmed unchanged in a
browser; **the RTL flip is not verified** — this browser does not re-resolve logical
properties on a `dir` change, shown with an isolated inline-styled element. A
person with `dir="rtl"` closes it.

**C4, two of three done.** `(auth)/accessible-authentication.test.tsx` covers 3.3.8
across all four pages, asserting the *values* rather than mere presence — a manager
offers a saved password for `current-password` and a generated one for
`new-password`, and swapping those is the failure that looks like it works. It also
asserts no CAPTCHA. `ui/Button.test.tsx` covers 2.5.8 against the variant strings,
because jsdom computes no layout and a rendered measurement there would be
measuring zeroes.

Four provocations, all failing correctly: stripping `autoComplete`, swapping
`current-password` for `new-password`, removing `sm`'s minimum height, and removing
the base's transparent border. **The third C4 test landed on 2026-09-28**, once the
2.4.11 fault had been reported, reproduced and fixed — `layout.test.ts` asserts the
scroll padding and its `xl` reset, both provoked.

**Checks for all of C:** `npm test`, `tsc`, `eslint`, `verify:css`, `verify:a11y`,
`verify:static`.

---

## D — Larger, each needing its own plan

### D1 · Error and loading boundaries — **done 2026-09-27**

- **Benefit:** a learner who hits a render error gets a page that says what
  happened and how to get out, instead of Next's unstyled default — and the
  project can state what it reports to Sentry rather than inheriting whatever the
  framework does.
- **Scope:** `global-error.tsx`, `(learner)/error.tsx`, the lesson `loading.tsx`,
  plus `captureException` and a test per boundary.
- **Dependencies:** ADR-031, accepted and now implemented. ADR-027 already in place.
- **Acceptance, all met:** each boundary renders with one `<h1>`; **the error's own
  message, digest and the address inside it are absent from the DOM**; the report
  fires exactly once; and `verify:static` still reports four prerendered routes,
  confirming no boundary pulled a static route dynamic.
- **Two things worth knowing for next time.** Reporting goes through
  `reportBoundaryError` in `lib/observability/sentry.ts`, not through the SDK — a
  test asserts that module is the only file in `frontend/` naming the vendor, and
  a boundary importing it directly would rightly fail. And `global-error.tsx`
  forced two guards to grow a pinned entry: it needs a raw `<h1>` and a plain
  `<a>`, because it replaces the document precisely when the design system and the
  router may be what failed.
- **Not verified in a browser.** Inducing a real render error means changing code
  to break it; the 11 tests cover the behaviour, and nobody has watched a learner
  hit one of these pages.
- **Approval:** granted with ADR-031.

### D2 · The 2.4.11 remedy — **done 2026-09-28**

- **Benefit:** focus is never hidden behind the floating navigation toggle.
- **Done with `scroll-pb-20 xl:scroll-pb-0` on `<html>`** — the first of ADR-030
  §3's three candidates, **not the one that would have reopened ADR-029's layout.**
  That option was listed as insufficient because scroll padding does nothing when
  an element is obscured without scrolling; that half turned out to be already
  covered by `SiteShell`'s footer `pb-24 xl:pb-8`. The two compose.
- **Acceptance, all met:** reproduced first (ADR-006), fixed, re-measured at zero
  overlaps, `scroll-padding-bottom` confirmed at `80px` below `xl` and `0px` above
  it, and `layout.test.ts` asserts both classes, each provoked.
- **One finding worth carrying:** the first attempt wrote the rule by hand as
  `@media (width < 80rem)` in `globals.css` and **the whole block was silently
  dropped from the compiled CSS.** Second time CSS has vanished without an error
  here. Prefer Tailwind utilities over hand-rolled media queries.
- **Approval:** not needed — the accepted layout is unchanged.

### D3 · `/me/courses/` pagination — **done 2026-09-27**

- **Benefit:** a learner with many enrolments sees all of them. Today the first
  page renders and the rest is dropped **silently**.
- **Scope:** a "load more" control plus tests. Prefer the button to page numbers —
  a learner's own course list is a short list they scan, not a table they navigate.
- **Dependencies:** none.
- **Acceptance, all met:** a second page is reachable and appends; a single-page
  response shows no control; the empty state is unaffected; a failed load keeps the
  list; a malformed `next` ends it quietly.
- **Two findings worth carrying.** The root cause was a **hand-written response
  type** omitting `next` — invariant 16 exists for this. And **`next` must not be
  followed**: Django builds it from the Host header, which the rewrite sets to its
  own destination, so it names the internal host. `cursorFrom` discards the origin,
  and the test fixtures carry `http://api/...` so a regression fails rather than
  passing on a convenient localhost URL. Any future paginated endpoint inherits
  both.
- **Approval:** granted.

### D4 · Caption language, end to end

- **Benefit:** the captions menu names its track, and assistive technology knows
  what language captions are in (WCAG 3.1.2).
- **Scope:** **backend first.** Model caption language, expose it, regenerate the
  schema and types, then add `srclang` and `label`.
- **Dependencies:** ADR-033 §3. **Blocked on backend modelling that is not
  scheduled**, and belongs to whichever milestone owns caption metadata.
- **Acceptance:** `srclang` and `label` come from the API. **Never hardcoded** — a
  guessed value would be wrong for exactly the courses that matter most, a
  beginner course captioned in the learner's language rather than the one taught.
- **Approval:** owner, plus a milestone home.

### D5 · Application-wide session-expiry response

- **Benefit:** a learner whose session expires is told, instead of finding out at
  their next action.
- **Scope:** needs a product decision before any code — a banner, a redirect to
  login preserving the destination, or a modal. Then one implementation.
- **Dependencies:** none technical. ADR-004 constrains the wording.
- **Approval:** owner. **This is a UX decision, not an implementation detail**,
  which is why no approach is recommended here.

---

## E — Blocked, and by what

| # | Work | Blocked on |
|---|---|---|
| **E1** | Rebuild-on-publish trigger for the static catalogue | Provisioning and spend. ADR-024 already records this: a rebuild trigger is a deploy hook, and the hook needs the environment. Hosting is chosen (ADR-025); **spend is still unapproved** |
| **E2** | Pricing page with a price; subscribe flow; a billing destination for `GRACE_PERIOD_ENDED` | CLAUDE.md §11 #1 — payment provider and jurisdiction. `PRICE_BOOK` stays `null` and its tripwire test stays |
| ~~**E3**~~ | ~~Any testing dependency~~ | **Unblocked 2026-09-28** — `axe-core` approved and adopted; `MSW` and `Playwright` declined, Playwright to be revisited at M8 |
| **E4** | A performance budget enforced in CI | **The owner.** A5 is done, and §11 sketches the shape: **350 KB gz per route**, about 7% above today's worst. Enforcing it means a script beside `verify:static` and `verify:css`, not a number in a document nobody runs |
| **E5** | Instructor UI | **An architectural decision that does not exist.** The API has no caller; administration runs through the Django admin (ADR-018, ADR-019). Whether a workflow belongs in a custom Next.js surface needs its own ADR — direct-to-R2 upload progress is the likeliest first candidate, because it is the one thing the Django admin genuinely cannot do |
| **E6** | Shareable filtered catalogue URLs | Not a bug — a consequence of ADR-024. Changing it is an ADR, not a refactor |

---

## F — Deferred product ideas

**None is approved.** Listed so nobody re-derives them, with what would justify
revisiting. **No design work belongs here until the trigger fires.**

| Idea | Revisit when |
|---|---|
| PWA installation | Learners ask for a home-screen launcher, or retention data shows repeat daily use. Cheap later; adds a manifest, a service worker and a caching policy to maintain |
| Offline media | A licensing decision permits it. **Conflicts with invariants 6 and 7** — playback goes browser→CDN by signed token, and a downloaded file is an unsigned copy. This is a rights question before an engineering one |
| Offline progress sync | Offline media exists. Needs conflict resolution, and the server owns completion (ADR-016) — a client that decided it offline would be the second definition the invariant forbids |
| Personalisation, recommendations | The catalogue is large enough that browsing fails. It is curated and small; recommending from a handful is worse than listing them |
| Feature flags, experiments | Two audiences to split, and traffic to make a result meaningful. Neither exists |
| AI features | A named product requirement. Nothing about the current model needs one |
| Live classes | CLAUDE.md §11 #2, still open. Would change M5's media modelling |
| Certificates, quizzes, assignments | Explicitly not approved requirements. Each adds a domain model, not just screens |
| Institutional themes | A B2B customer. Would mean per-tenant tokens, and ADR-032's single-mechanism theme is the thing that would have to give |

---

## The order, if you want one line

**A1 today** — ten minutes, and still the only unverified claim from four stages of
redesign. Then **C3, C4, and plan D1**. **A2 next**, because D2 cannot be scoped
until it says what the fault is; **A3 and A4** close out the two fixes that shipped
on specification rather than observation. D3 and D5 each want their own
conversation; D4 needs backend modelling. E waits on you or on money; F waits on
evidence.

No item is waiting on a decision any more.
