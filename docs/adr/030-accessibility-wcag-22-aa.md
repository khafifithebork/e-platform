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
principle: of the six success criteria 2.2 adds at AA, **five appeared already satisfied and
one was a genuine failure** — 2.4.11 Focus Not Obscured (Minimum), below the `xl`
breakpoint. It was reported by the owner, reproduced, and fixed on 2026-09-28.

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
| **2.4.11 Focus Not Obscured (Minimum)** | AA | **Was the one real failure. Reported by the owner, reproduced, fixed 2026-09-28.** `SiteNavTree`'s `fixed bottom-5 left-5` button hid the focus ring of anything Tab scrolled to the bottom edge. `scroll-pb-20 xl:scroll-pb-0` on `<html>`; see §3 |
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

## 3. The 2.4.11 failure — reported, reproduced, fixed 2026-09-28

The owner found it with a keyboard: the focus ring disappearing behind the "Site
map" button. Then it was reproduced and measured, per ADR-006 — a remedy for a
fault nobody has seen is a change nobody can verify.

**The mechanism.** Tab moves focus to an element below the fold, and the browser
scrolls it in *minimally* — `block: "nearest"` — which parks it flush against the
bottom edge, exactly where the fixed button sits. At **420×480 on `/courses`,
three focusable elements** landed under it: the course card's link and both footer
links. `scroll-padding-bottom` computed to `auto`.

**The fix, and why it is the first option rather than the third.** Of the three
remedies originally listed here, `scroll-padding-bottom` was noted as not helping
"when focus lands without scrolling". That gap turned out to be already covered:
`SiteShell`'s footer has carried `pb-24 xl:pb-8` since the redesign, reserving the
space at the page's end. **The two compose**, and neither is sufficient alone — so
the option that keeps ADR-029's accepted layout was enough, and the one that would
have reopened it was not needed.

`scroll-pb-20 xl:scroll-pb-0` on `<html>`. 5rem clears the button's bottom 62px;
above `xl` it resets to zero, because there the navigation is a static rail and
leaving the padding would stop every keyboard scroll short of the viewport edge for
no reason.

**After: zero overlaps at the same size, and `scroll-padding-bottom` computes to
`80px`.** Same probe, same page, same viewport as the reproduction.

### The first attempt vanished without an error

Written first as a hand-rolled `@media (width < 80rem) { :root {
scroll-padding-bottom: 5rem } }` in `globals.css`. **The entire block was dropped
from the compiled stylesheet** — the rules either side of it survived, nothing
failed, and the page behaved exactly as before. The range syntax is what did it.

That is the second time CSS has silently disappeared in this codebase, after the
`[--token]` form that meant 45 classes never applied in any release. Both times the
only thing that caught it was measuring the result rather than trusting the diff.
Tailwind utilities go through its own breakpoints and cannot fail that way, and
`src/app/layout.test.ts` asserts the classes are present.

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

**Added 2026-09-27, no dependency:**

1. **3.3.8** — `(auth)/accessible-authentication.test.tsx`. Asserts every auth field
   sets `autoComplete`, and the *values*: a manager offers a saved password for
   `current-password` and a generated one for `new-password`, and swapping those is
   the failure that looks like it works. Also asserts no CAPTCHA. The regression it
   guards is a plausible one — stripping `autocomplete` from a login form looks like
   hardening and breaks exactly what this criterion relies on.
2. **2.5.8** — `ui/Button.test.tsx`. Asserts each size keeps a minimum height at or
   above 24px, against the variant strings rather than a rendered box, because jsdom
   computes no layout.

**Added 2026-09-28:**

3. **2.4.11** — ~~once reproduced~~ **done 2026-09-28**. `src/app/layout.test.ts`
   asserts the scroll padding and its `xl` reset, each provoked. The fault was
   reported by the owner, then reproduced and measured before anything changed.

**Requires a person, and cannot be delegated to a scan:**

- Keyboard walk of every route, including the drawer and the player.
- A screen reader on the lesson page: is the transcript navigable, are cue
  changes announced without flooding.
- 200% zoom and 320 CSS px reflow (1.4.10), at which the lesson layout's two
  columns must collapse.
- ~~`prefers-reduced-motion` in a real browser~~ — **confirmed in full 2026-09-28**,
  hero and scroll-triggered sections both. See §6. Re-check after any change to
  `MotionProvider`, `Reveal` or `StaggerList`.
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

**No conformance claim is made, but one item is now closed.** The reduced-motion fix
shipped in PR #71 was **confirmed in full on 2026-09-28** — the owner checked it in
Firefox, both the hero (which animates on mount) and the scroll-triggered sections
below it (`whileInView` and an `IntersectionObserver`). That was the fault that
started this workstream, and it is the first thing here established by a person
rather than argued from a passing test.

The agent could not have closed it: its browser reports `document.hidden` even when
fronted, so `requestAnimationFrame` is frozen at zero frames per second and Motion
cannot animate in it at all.

**Everything else in §4's human column is still outstanding.** Adopting 2.2 AA is a
commitment to a target and a verification procedure; it remains not a statement that
the product conforms, and this file must not be cited as one.

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
