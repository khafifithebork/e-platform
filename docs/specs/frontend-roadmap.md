# Frontend roadmap — the remaining gaps, in dependency order

**Status:** written 2026-09-27 and **substantially overtaken the same day.**
**Depends on:** nothing outstanding — **all four ADRs were accepted by the owner on
2026-09-27**, and two of the four defects were fixed in the process.

| ADR | Status | Left to do |
|---|---|---|
| ADR-030 — WCAG 2.2 AA | **accepted** | C3 done; two of C4's three tests done; D2 once A2 reproduces the fault |
| ADR-031 — boundaries | **accepted** | D1, which wants a plan first |
| ADR-032 — theme, toggle declined | **accepted** | nothing. §2's defect fixed; A4 still confirms it |
| ADR-033 — localisation deferred | **accepted** | §3's `<track>` gap, blocked on backend (D4) |

**Two of the four defects are fixed**: `color-scheme` is declared, and
inline-direction utilities are logical with a pinned guard. **Two remain** — no
error or loading boundaries (D1), and `/me/courses/` pagination (D3).

**C3 and two of C4's three tests also landed on 2026-09-27**, so the only remaining
work behind an accepted ADR is D1, the 2.4.11 remedy once A2 has reproduced it, and
the two open defects. Section A has not been touched and still needs a person.

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

### A1 · Reduced motion in a real browser — **do this first**

- **Benefit:** confirms the landing page is not blank for visitors who asked for
  less motion. Until stage 2 it was — entirely, for exactly those people.
- **Scope:** ten minutes. `docs/runbooks/accessibility-verification.md` §3.1.
- **Dependencies:** none. **Outstanding since 2026-09-25.**
- **Acceptance:** headline, subtitle, both calls to action, course cards and all
  four feature panels visible with the OS reduced-motion setting on; runbook §6
  gains its first row.
- **Why it cannot be automated here:** the agent's browser reports
  `document.hidden` even when fronted, so `requestAnimationFrame` is frozen and
  that pane cannot tell a working page from a broken one.
- **Approval:** none. **A person with a browser.**

### A2 · Keyboard pass, and reproduce 2.4.11

- **Benefit:** either finds the one real WCAG 2.2 gap or rules it out.
- **Scope:** runbook §3.2 across nine routes, narrow viewport especially.
- **Acceptance:** each route walked; 2.4.11 either reproduced with a recorded
  route and width, or recorded as not reproducible.
- **Gates:** C4 and D2. **Do not fix 2.4.11 before reproducing it** (ADR-006).
- **Approval:** none.

### A3 · Forced colours

- **Benefit:** confirms the `outline-hidden` fix held and `Notice` stays readable.
- **Scope:** runbook §3.5.
- **Acceptance:** focus visible on `<main>` and the drawer; notices
  distinguishable; current-page state survives.
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

### A5 · Per-route first-load JS

- **Benefit:** makes a performance budget possible. Without it any threshold is
  invented.
- **Scope:** obtain per-route figures — Next 16 no longer prints them in the build
  output used for the baseline in `frontend-state-and-api.md` §11, so this needs
  the build manifest or a bundle analyser run locally (not a dependency).
- **Acceptance:** a per-route table, and **then** a proposed ceiling for the lesson
  route, which is the only dynamic one and the one a learner waits on.
- **Gates:** E4.
- **Approval:** none to measure. A budget that gates CI needs the owner.

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

### B2 · Resolve the architecture.md §8.2 discrepancy

- **Benefit:** ends a documented-versus-code contradiction. architecture.md names
  MSW, `@axe-core/react` and Playwright; **none is installed.**
- **Scope:** either approve one or more under §5, or record §8.2's frontend line as
  superseded by the guards that exist.
- **Acceptance:** architecture.md and `package.json` agree, one way or the other.
- **Approval:** owner. §5 if any dependency is adopted.
- **My recommendation:** `axe-core` in the Vitest run is the one with real
  marginal value — it walks a rendered tree and catches what structural greps
  cannot. Playwright is a bigger commitment than a small team needs while the
  product has one dynamic route. MSW would replace a working `fetch` stub for no
  gain I can demonstrate.

---

## C — Small fixes, each behind an ADR

All small. Each needs its ADR accepted first, and each needs a provoked guard
(ADR-006) before it is believed.

| # | Fix | Waits on | Size |
|---|---|---|---|
| ~~**C1**~~ | ~~Declare `color-scheme` on `:root`~~ | **Done 2026-09-27** — split out of ADR-032 by the owner | shipped with 5 provoked tests |
| ~~**C2**~~ | ~~Four physical→logical utility swaps~~ | **Done 2026-09-27** — six, not four; split out of ADR-033 | shipped with a pinned guard |
| ~~**C3**~~ | ~~`contrast.test.ts` cites 2.2 AA~~ | **Done 2026-09-27** | no new arithmetic — 2.2 changes no contrast threshold |
| **C4** | ~~`autoComplete` on auth fields (3.3.8)~~ **done**; ~~button minimum heights ≥24px (2.5.8)~~ **done**; the 2.4.11 remedy | **two of three done 2026-09-27**; the third still needs A2 | 13 assertions, all provoked |

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
the base's transparent border. **The third C4 test still waits on A2** — there is no
remedy to test until the fault is reproduced.

**Checks for all of C:** `npm test`, `tsc`, `eslint`, `verify:css`, `verify:a11y`,
`verify:static`.

---

## D — Larger, each needing its own plan

### D1 · Error and loading boundaries

- **Benefit:** a learner who hits a render error gets a page that says what
  happened and how to get out, instead of Next's unstyled default — and the
  project can state what it reports to Sentry rather than inheriting whatever the
  framework does.
- **Scope:** `global-error.tsx`, `(learner)/error.tsx`, the lesson `loading.tsx`,
  plus `captureException` and a test per boundary.
- **Dependencies:** **ADR-031 accepted 2026-09-27 — ready to plan.** ADR-027 already in place.
- **Acceptance:** each boundary renders with one `<h1>`; **the error's own message
  is absent from the DOM**; `captureException` called once; `verify:static` still
  reports four prerendered routes, proving no boundary pulled a static route
  dynamic.
- **Approval:** owner. No dependency, no cost.

### D2 · The 2.4.11 remedy

- **Benefit:** focus is never hidden behind the floating navigation toggle.
- **Scope:** unknown until A2. ADR-030 §3 lists three candidates; **the tidiest
  one moves the toggle and reopens a layout ADR-029 accepted**, which is why this
  is here and not in C.
- **Dependencies:** **ADR-030 accepted**; still needs A2 to know what the fault is.
- **Acceptance:** reproduced first, then fixed, then a test for the chosen remedy.
- **Approval:** owner if the remedy changes the accepted layout.

### D3 · `/me/courses/` pagination

- **Benefit:** a learner with many enrolments sees all of them. Today the first
  page renders and the rest is dropped **silently**.
- **Scope:** a "load more" control plus tests. Prefer the button to page numbers —
  a learner's own course list is a short list they scan, not a table they navigate.
- **Dependencies:** none. Not urgent: no real learner has enough enrolments yet.
- **Acceptance:** a second page is reachable; a single-page response shows no
  control; the empty state is unaffected.
- **Approval:** owner, as it adds an interaction.

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
| **E3** | Any testing dependency | B2 |
| **E4** | A performance budget enforced in CI | A5 |
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
