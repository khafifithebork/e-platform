# ADR-030 — WCAG 2.2 AA, and the one criterion we might already fail

**Status:** accepted by the owner 2026-09-27
**Date:** 2026-09-27
**Decides:** the accessibility target, which architecture.md sets at 2.1 AA and
no ADR has ever stated
**Supersedes:** architecture.md's 2.1 AA accessibility baseline, on the level only.
§8.2's frontend tooling line was separately revised on 2026-09-28 when the owner
adopted `axe-core` and declined `MSW` and `Playwright` — see §5
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

## 2a. The criteria §2 never looked at — **added 2026-10-03**

**§2 measured what 2.2 *adds*. It never measured what 2.2 *inherits*,** and the
difference matters more here than it would almost anywhere else.

The reasoning in §1 was: the repository "has been working to 2.1 AA", so moving to
2.2 only needs the six new criteria checked. The evidence offered for the 2.1 AA
baseline is `contrast.test.ts` — which computes colour ratios and nothing else. So
the ~44 AA criteria 2.2 carries forward from 2.0 and 2.1 were adopted on the
strength of a test that checks one of them.

**The gap this leaves is the whole of 1.2 Time-based Media, in a product whose
primary content is video.** Searched before claiming it: no document in this
repository mentions 1.2.1, 1.2.2, 1.2.3, 1.2.4 or 1.2.5 — not this ADR, not
`architecture.md` §8.2, not the verification runbook. The owner asked about audio
descriptions on 2026-10-03, which is how this surfaced; it should not have taken a
question.

### What is actually in place, verified against the code

| Criterion | Level | State |
|---|---|---|
| **1.2.1 Audio-only and Video-only (Prerecorded)** | A | **Unassessed, and it has a concrete subject**: `LessonType.AUDIO` is a modelled lesson type, and an audio-only lesson needs a text alternative. A `TARGET` transcript probably *is* that alternative, but nothing in the product says so, no test asserts it, and the player's transcript panel is presented as a reading aid rather than as the alternative — which is a UI question, not only a data one |
| **1.2.2 Captions (Prerecorded)** | A | **Partial, and weaker than it looks.** `LessonPlayer` emits `<track kind="captions">` from `approved_transcript_for`, with `srcLang` and `label` since ADR-033 §3a. But the source is a *transcript of speech* — Deepgram output, then instructor edits. Captions must also convey non-speech audio and identify speakers. Calling a speech transcript "captions" in the `kind` attribute is a claim the content may not support |
| **1.2.3 Audio Description or Media Alternative** | A | **Unassessed.** Satisfiable by a full text alternative rather than audio, which may be the cheaper route — see below |
| **1.2.4 Captions (Live)** | AA | **Inapplicable today.** There is no live content. It arrives with live classes, which are CLAUDE.md §11 row 2 ("whether live classes are on the roadmap") and still open — so this criterion is a cost attached to that decision, and belongs in the argument when it is made |
| **1.2.5 Audio Description (Prerecorded)** | AA | **Not implemented, and not currently assessable.** Nothing in the model, nothing in the player. The reason it cannot be closed is below, and it is not an owner preference |

### Why 1.2.5 cannot be answered yet, and what it is not blocked on

**It is blocked on content not existing, not on a decision.** Whether a video needs
audio description is a property of the footage: the criterion applies where visual
information is not already available in the audio. There is no lesson media to look
at — `MediaAsset` rows exist only in test fixtures — so the question has no subject.

For language teaching the answer is genuinely unpredictable per lesson, and the
likeliest failure is specific: **showing mouth and tongue position for
pronunciation is a real teaching technique whose entire content is visual.** A
talking-head grammar explanation may be fully carried by its soundtrack and need
nothing. A lesson that writes on screen, mimes vocabulary, or demonstrates
articulation is not, and no amount of transcript fixes it.

So this is not "deferred pending owner input". It is **answerable the moment the
first real lesson is uploaded, and unanswerable before** — which makes the upload
the right gate, not a date.

### What implementing it would need — and three capability claims I am not making

The data model does not accommodate it. Verified: `TranscriptKind` is `TARGET` and
`TRANSLATION` only; `MediaAsset` is `OneToOneField` to a lesson with no variant or
rendition concept; `Transcript` holds text segments, and audio description is
audio, so forcing it into `Transcript` would be modelling it as the thing it is not.

Three routes exist, and each turns on a fact **this ADR does not assert** (CLAUDE.md
§6 — a provider or browser capability I have not checked is not something to write
down as true):

1. **`<track kind="descriptions">`.** In the HTML spec. My understanding is that no
   major browser surfaces it to users, which would make this route decorative —
   **needs verification before anyone plans around it.**
2. **A described audio rendition on the video asset.** Whether Mux supports
   additional audio tracks, and at what cost, is **unverified** and has a bill
   attached either way (§5).
3. **A media alternative in text** — a full description of the visual content
   alongside the transcript. This satisfies 1.2.3 at Level A but **not 1.2.5 at
   AA**, which specifically wants audio description. Cheapest, and only a partial
   answer.

### What this section changes now

Nothing in code. It converts an unexamined assumption into a written gap, which is
the same thing §6 does for the human verification column. Concretely:

- **§6's prohibition is now broader than it was.** This ADR could already not be
  cited as a conformance claim. It additionally cannot be cited as evidence that
  the inherited AA criteria were *examined* — only the six new ones were.
- **A full 2.2 AA pass against all ~50 AA criteria is outstanding work**, not a
  box this ADR ticked. It belongs in the runbook, scoped and sized.
- **The first real lesson upload is a gate**: at that point 1.2.1, 1.2.3 and 1.2.5
  become answerable, and the answer may carry a per-lesson production cost that is
  a §5 matter rather than an engineering one.

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
| `src/test/accessibility.test.tsx` | **axe over every primitive and four domain components**, in each state they have — ARIA validity, name and role, label association, duplicate ids, nesting. Adopted 2026-09-28; see §5 for which rules it deliberately does not run |
| `src/app/layout.test.ts` | 2.4.11's scroll padding and its `xl` reset; 3.1.1's `lang` |

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
- ~~`forced-colors: active`, which ADR-029's palette cannot be reasoned about.~~
  **Confirmed in full by the owner on 2026-09-28** — focus ring, `Notice`'s symbol,
  and the current-page state. The focus ring is the one that mattered most, because
  it guards a real earlier fix: `outline-none` in Tailwind 4 dropped the
  transparent-outline fallback a high-contrast mode turns visible, and
  `outline-hidden` restored it. **That difference is invisible outside such a mode**,
  so no test in this repository could ever have shown it holding. Re-check after any
  change to the palette, to `Notice`, or to how the current page is marked.
- Caption accuracy, which is a human review step in the transcript workflow
  (ADR-014, ADR-015) and not a frontend concern.

`docs/runbooks/accessibility-verification.md` is the procedure.

---

## 5. What we verify *with* — resolved 2026-09-28

architecture.md §8.2 named `@axe-core/react`, `MSW` and `Playwright`, and **none of
the three was installed**. This section recorded that rather than resolving it,
because the choice was the owner's under §5. It has now been made, and §8.2 carries
the revision.

**`axe-core` adopted.** Not `@axe-core/react`: that package logs to the browser
console in development, which helps a human watching and fails nothing, while
`axe-core` called from a test either passes or does not. It has **no dependencies of
its own** and **does not reach the client bundle** — asserted against the built
chunks, not assumed.

**`MSW` and `Playwright` declined for now**, with reasons recorded in §8.2. Playwright
is worth revisiting at M8, when there is a checkout worth walking end to end.

### What it added, and what it cannot

`src/test/axe.ts` switches off two families of rule rather than leaving them to
report nothing, because a rule that silently never fires is worse than no rule:
`color-contrast`, which `contrast.test.ts` already computes from the tokens for both
schemes, and the page-level structure rules, which `verify:a11y` checks on built HTML
where they are real. A component fragment legitimately has no `<main>` and no `<h1>`.

So the layer this adds is the markup itself — ARIA validity, a widget's name and
role, label association, duplicate ids, nesting. **Narrower than "we run axe", and
true.**

**It earned its place on the first run.** `Field` had `role="alert"` on its `<ul>` of
error messages. An explicit role replaces the implicit one, so the list stopped being
a list while still containing `<li>` children with nothing to belong to — reported as
`aria-allowed-role` and `listitem`. `Field.test.tsx` passed before and after the fix,
because it asserted that an alert exists and contains the message, which was true
either way. Neither the structural greps nor a human reading the JSX had caught it.

Provoked both directions: restoring the old markup fails, and a dangling
`aria-controls` on `Curriculum`'s accordion is caught as `aria-valid-attr-value`.

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

**And since 2026-10-03 it cannot be cited as evidence of examination either.** §2a
records that only the six criteria 2.2 *adds* were ever checked; the ~44 AA criteria
it inherits were assumed from a contrast test. The whole of 1.2 Time-based Media —
in a video product — had never been looked at.

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
5. **Added 2026-10-03.** The inherited AA criteria are either passed criterion by
   criterion in the runbook, or listed as unexamined. 1.2.1, 1.2.3 and 1.2.5 are
   re-opened at the first real lesson upload, because that is when they acquire a
   subject — not on a date.

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
