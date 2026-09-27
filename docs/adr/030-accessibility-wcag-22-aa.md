# ADR-030 — WCAG 2.2 AA, and the one criterion we might already fail

**Status:** accepted by the owner 2026-09-27
**Date:** 2026-09-27
**Decides:** the accessibility target, which architecture.md sets at 2.1 AA and
no ADR has ever stated
**Supersedes:** architecture.md's 2.1 AA accessibility baseline, on the level
only. Everything else in §8.2 stands, including the unresolved tooling question
in §5 below
**Depends on:** architecture.md §8.2 and its accessibility line, ADR-006
(provoke every control), ADR-023 §1 (a decision is not a control until something
asserts it), ADR-024 (the public catalogue stays static), ADR-029 (visual
refresh)

---

## Decision

**WCAG 2.2 AA is the target, and the move from 2.1 costs almost nothing.**

Checked criterion by criterion against the implementation rather than adopted on
principle: of the six success criteria 2.2 adds at AA, **five appear already
satisfied and one is a genuine risk** — 2.4.11 Focus Not Obscured (Minimum),
below the `xl` breakpoint only.

This ADR also splits the checks into what a machine can decide and what a person
must, because conflating the two is how a project comes to believe an automated
scan is a conformance claim.

---

## 1. Why this needs a decision at all

`docs/architecture.md` §8.2 commits to an accessibility baseline and the
repository has been working to **2.1 AA** — `src/app/contrast.test.ts` says so in
its own docstring, and computes 4.5:1 and 3:1 from the tokens for both colour
schemes. No ADR records the target, so nothing distinguishes "the level we chose"
from "the level whoever wrote that test assumed".

2.2 is the current W3C Recommendation. Naming it is cheap here because the
existing work already reaches most of it, and naming it now is cheaper than
discovering the gap during a launch review.

**The contrast thresholds do not change between 2.1 and 2.2.** `contrast.test.ts`
stays exactly as it is; only its docstring's citation needs updating, and that is
a one-line edit in whichever change implements this.

---

## 2. What 2.2 adds, measured against this repository

Each row was checked against the code, not recalled.

| Criterion | Level | Finding |
|---|---|---|
| **2.4.11 Focus Not Obscured (Minimum)** | AA | **The one risk.** `SiteNavTree` renders a `fixed bottom-5 left-5 z-40` "Site map" button. A focused control at the foot of a long page can sit behind it. Scoped: the button is `xl:hidden`, so this is below `xl` only |
| 2.4.12 Focus Not Obscured (Enhanced) | AAA | Out of scope |
| 2.4.13 Focus Appearance | AAA | Out of scope. Worth noting the global ring is already 2px at 2px offset |
| **2.5.7 Dragging Movements** | AA | Appears satisfied. The only drag is the video element's native seek bar, and `TranscriptPanel` offers click-to-seek on any cue — a single-pointer alternative to scrubbing |
| **2.5.8 Target Size (Minimum)** | AA | Appears satisfied. 24×24 CSS px is the floor; the smallest control **measured in a browser** was the header's "Sign in" at 34px. The enrolment card's resume link was 36px when hand-written and is ≥40px by construction now it uses the `sm` variant's `min-h-10` — that one is derived from the variant, not measured, because reaching it needs a session and data |
| **3.2.6 Consistent Help** | AA | Inapplicable. The criterion applies only where a help mechanism exists, and the product has none |
| **3.3.7 Redundant Entry** | AA | Appears satisfied. Registration asks for email and password once — there is no confirm-password field — and the reset flow never asks for information already given |
| **3.3.8 Accessible Authentication (Minimum)** | AA | Appears satisfied. No CAPTCHA, no puzzle, and every field sets `autoComplete` (`email`, `current-password`, `new-password`), so a password manager can fill the form |

**"Appears satisfied" is deliberate wording.** Five of these are reasoned from
the source and from measurements taken in a browser. None is asserted by a test,
which by ADR-023 §1 means none is a control yet. §4 says which become tests.

---

## 3. The 2.4.11 risk, stated precisely

The floating toggle is positioned relative to the viewport, so it does not move
when the page scrolls. Tab to a link low on `/courses` on a narrow screen and the
focused element may be entirely behind it. The criterion permits partial
obscuring only where the author has not caused it; a fixed overlay the author
placed is exactly what it addresses.

Three candidate remedies, none adopted here because this is a target decision and
not an implementation:

| Option | Trade |
|---|---|
| `scroll-padding-bottom` on the scroll container | One line, keeps the design, and does not help when focus lands without scrolling |
| Hide the toggle while focus is inside the page content | Sound, and a behaviour somebody has to maintain |
| Move the toggle into the header for narrow screens | Removes the class of problem, and reopens a layout ADR-029 accepted |

**Whoever implements this must first reproduce it.** ADR-006's rule applies to
accessibility findings as much as to security ones: a remedy for a fault nobody
has seen is a change nobody can verify.

---

## 4. Automated, and not

The distinction matters more than the list. A machine can check structure and
arithmetic. It cannot check whether a focus ring is *visible on this background
to this person*, whether an error message *explains* anything, or whether a
caption is *correct*.

**Already automated, in CI:**

| Check | Guards |
|---|---|
| `src/app/contrast.test.ts` | 1.4.3 and 1.4.11 arithmetic, both schemes, from the tokens |
| `verify:a11y` (`scripts/assert-page-structure.mjs`) | one `<h1>`, one `<main>`, heading order, `lang`, `alt` — on built HTML, 11 pages |
| `verify:css` (`scripts/assert-css-tokens.mjs`) | tokens actually resolve, so a focus ring or a border cannot silently vanish |
| `SiteNavTree.test.tsx` | 2.1.2 focus containment, focus restoration, scroll-lock release |
| `Field.test.tsx` | 1.3.1, 3.3.1, 4.1.3 — label association, `aria-invalid`, `role="alert"` |
| `PageTitle.test.tsx` | one heading treatment, no hand-written `<h1>` |

**Proposed additions, all without a dependency:**

1. **3.3.8** — assert every auth field sets `autoComplete`. A future "security
   hardening" that strips it would break password managers, which is the failure
   this criterion exists for, and nothing would notice today.
2. **2.5.8** — assert the `sm` and `md` button sizes keep a minimum height at or
   above 24px. A unit assertion on the variant strings, not a rendered
   measurement, so it is cheap and stable.
3. **2.4.11** — once reproduced, a test for whichever remedy is chosen.

**Requires a person, and cannot be delegated to a scan:**

- Keyboard walk of every route, including the drawer and the player.
- A screen reader on the lesson page: is the transcript navigable, are cue
  changes announced without flooding.
- 200% zoom and 320 CSS px reflow (1.4.10), at which the lesson layout's two
  columns must collapse.
- `prefers-reduced-motion` in a real browser — **still outstanding**, see §6.
- `forced-colors: active`, which ADR-029's palette cannot be reasoned about.
- Caption accuracy, which is a human review step in the transcript workflow
  (ADR-014, ADR-015) and not a frontend concern.

`docs/runbooks/accessibility-verification.md` is the procedure.

---

## 5. Blocked: what we verify *with*

architecture.md §8.2 names `@axe-core/react` for accessibility assertions,
`MSW` for API mocking and `Playwright` for end-to-end journeys. **None of the
three is in `package.json`.** The repository stubs `fetch` directly and
`contrast.test.ts` states plainly that axe "is a §5 dependency decision that has
not been made".

That is a document disagreeing with the code, so per CLAUDE.md §2 it is reported
and not silently resolved. Two ways out, and the owner picks:

- **Approve `@axe-core/react` (or `axe-core` in the Vitest run) under §5.** It
  walks a rendered tree and catches classes of fault the structural guards
  cannot — a `<div>` with a click handler, a mislabelled control, a duplicated
  landmark inside a component rather than a page.
- **Record §8.2's frontend line as superseded** by the guards that actually
  exist, and accept that the rendered-tree class of fault is caught by the human
  pass instead.

**This ADR did not need that answered to stand, and it was accepted without it.**
The target is the decision; the tooling is a separate approval, **still open as of
2026-09-27**. Everything in §4's "already automated" column exists today with no
dependency at all, so acceptance of this ADR changes nothing about what is
installed.

---

## 6. One thing this ADR does not let us claim

**No conformance claim is made, and one item is outstanding.** The
reduced-motion fix shipped in PR #71 has never been observed working in a
browser: the only browser available to the agent reports `document.hidden` even
when fronted, so `requestAnimationFrame` is frozen at zero frames per second and
Motion cannot animate in it. React's hydration error is gone — that is verified —
but "the content becomes visible for a reduced-motion visitor" is a different
claim and remains unverified.

Adopting 2.2 AA is a commitment to a target and a verification procedure. It is
not a statement that the product currently conforms, and this file must not be
cited as one.

---

## Consequences

**Positive.** The target is written down instead of inferred from a test
docstring. Five of six new criteria turn out to be satisfied already, so the
commitment is honest rather than aspirational. Three cheap tests convert reasoned
claims into controls.

**Negative.** 2.4.11 is a real fault to fix, and the tidiest remedy reopens a
layout ADR-029 accepted. The human pass is recurring work with no automation to
absorb it — which is the point, but a small team should size it before promising
it per release.

**UX and responsive.** 1.4.10 reflow at 320px and the 2.4.11 remedy both bear on
the narrow-screen lesson layout, which is the densest surface in the product.

**Security and performance.** None. No dependency, no bundle change, no data
handling. Note that 3.3.8 pulls in the opposite direction from a reflexive
"disable autofill on auth forms" instinct, and this ADR settles that in favour of
the criterion.

---

## Verification criteria

1. `contrast.test.ts` cites 2.2 AA and still passes unchanged.
2. The three proposed tests exist, and each was provoked before being believed.
3. The runbook exists and names an owner for the human pass.
4. 2.4.11 is either reproduced and fixed, or recorded as an accepted open fault
   with a date — not left implicit.

## Related

ADR-006, ADR-023, ADR-024, ADR-029, ADR-031 (boundaries: an error state is also
an accessibility state), ADR-033 (language metadata is 3.1.1 and 3.1.2).
`docs/runbooks/accessibility-verification.md`, `docs/design-system.md`.

**Approval:** granted by the owner on 2026-09-27. §5 approval for any testing
dependency is separate, was not requested here, and remains outstanding — see §5.

**What acceptance does and does not authorise.** It fixes the target and the
verification split. It does not by itself authorise the code changes that follow
from it: the three tests in §4 and the 2.4.11 remedy are tracked as items C3, C4
and D2 in `docs/specs/frontend-roadmap.md`, and D2 in particular may reopen a
layout ADR-029 accepted, which needs its own decision.
