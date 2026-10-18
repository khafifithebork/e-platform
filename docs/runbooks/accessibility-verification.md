# Runbook — verifying accessibility

**Status: written; §3.1 and §3.5 passed in full, §3.2's 2.4.11 check done — all
2026-09-28.** Written 2026-09-27 alongside ADR-030. **Still unwalked:** the rest of
§3.2's keyboard pass, §3.3's screen reader, and §3.4's zoom and reflow. See §6.

Treat every step in §3 as a plan rather than a tested procedure. `rollback.md`
found its own §3 wrong the first time it was walked; assume this one has the same
kind of error in it until somebody has been through it.

**Target: WCAG 2.2 AA (ADR-030).** That ADR has the criterion-by-criterion
reasoning; this file is only the procedure.

---

## 1. What already runs, and what it cannot tell you

`make lint`, `npm test` and the three `verify:*` scripts run in CI on every push.
**Read this before doing anything by hand** — there is no point walking a page
for something a guard already covers.

| Check | Covers | Blind to |
|---|---|---|
| `contrast.test.ts` | 1.4.3, 1.4.11 arithmetic, both schemes, from the tokens | Anything not expressed as a token — a hardcoded colour, an image, text over a gradient |
| `verify:a11y` | One `<h1>`, one `<main>`, heading order, `lang`, `alt`, across 11 **built** pages | The lesson route (dynamic, so absent from the build output), and every error or loading state, which render only on failure |
| `verify:css` | Tokens resolve, so a focus ring or border cannot silently vanish | Whether the resolved value is *visible* against its background |
| `SiteNavTree.test.tsx` | 2.1.2, focus restoration, scroll-lock release on resize | Whether the drawer is usable with a screen reader |
| `Field.test.tsx` | Label association, `aria-invalid`, `role="alert"` | Whether the message says anything useful |
| `PageTitle.test.tsx` | No hand-written `<h1>` anywhere in `src/` | Whether the heading text describes the page |

**A green suite is not a conformance claim.** ADR-030 §6 is explicit about this
and so is this runbook: the automated column above is structure and arithmetic.
Everything in §3 needs a person.

---

## 2. Before you start

```bash
cd frontend && npm run build && npm run verify:a11y && npm run verify:css
```

Then serve the built app rather than `next dev` — the development overlay
intercepts focus and injects markup, and you will spend an hour on an artefact:

```bash
cd frontend && npm start
```

You need the API running for the learner surface. `make dev` brings up the stack.

**Record what you tested on.** Browser, version, OS, and screen reader with its
version. A finding without that is not reproducible, and screen-reader behaviour
differs more between versions than between pages.

---

## 3. The passes that need a person

Each is a separate sitting. Do not try to do all five at once — they use different
attention and the mistakes cross over.

### 3.1 Reduced motion — **confirmed 2026-09-28, in full**

Turn on the OS setting (Windows: Settings → Accessibility → Visual effects →
Animation effects off; macOS: Accessibility → Display → Reduce motion), then open
`/`.

**Confirm the headline, subtitle, both calls to action, the course cards and all
four feature panels are visible.**

This is not a cosmetic check. Until PR #71 the landing page rendered **entirely
blank** for reduced-motion visitors: ten components branched on
`useReducedMotion()` during render, the server emitted the animated branch with
`opacity: 0` inline, and React declined to patch the mismatch. A unit test
asserted the branch and passed the whole time because it mocked the hook.

**Confirmed in full on 2026-09-28**, by the owner in Firefox, in two passes because
the page uses two mechanisms:

- The headline, subtitle and both calls to action come from `Hero`, which animates
  **on mount**. Seeing the headline is what proves the hydration fix — the mismatch
  is what left `opacity: 0` stuck inline, so a visible headline means server and
  client agree.
- The featured course cards and the four "what you get" panels use `Reveal` and
  `StaggerList`, driven by **`whileInView` and an `IntersectionObserver`**. Those
  needed a scroll, and they appear.

**Re-check this after any change to `MotionProvider`, `Reveal` or `StaggerList`**,
because no automated check can. The agent's browser reports `document.hidden` even
when fronted, so `requestAnimationFrame` is frozen at zero frames per second and
Motion cannot animate in it at all — that pane cannot distinguish a working page
from a broken one, which is why this section exists as a human step rather than a
test.

Also check `prefers-reduced-motion` on `/courses/[slug]` (the `Reveal` sections)
and the enrolment list (`StaggerList`).

### 3.2 Keyboard, every route

Tab through with no mouse. Routes: `/`, `/courses`, a course, `/pricing`,
`/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`,
`/my-courses`, a lesson.

**`/verify-email` is the one with two forms on a page** (added 2026-09-28), so it is
where a keyboard order can go wrong: Tab should reach the token field, the verify
button, then the resend address and its button, in that order, with nothing skipped
between the two `<form>` elements.

- Focus is **visible at every stop**. The global ring is 2px at 2px offset; if you
  cannot see it somewhere, that is a finding, not your eyesight.
- The skip link is the first stop and lands focus on `<main>`.
- **2.4.11 — found and fixed 2026-09-28.** The owner tabbed to a control low on a
  page and the focus ring was behind the fixed "Site map" button. Reproduced at
  420×480 on `/courses` (three elements overlapped), fixed with
  `scroll-pb-20 xl:scroll-pb-0` on `<html>`, and re-measured at zero. **Still worth
  re-checking here**, because the fix is scroll padding and a future fixed element
  at a different edge would not be covered by it.
- The drawer: opens, traps Tab, `Escape` closes and returns focus to the toggle,
  and page scrolling comes back. Resize to desktop while open — it should close
  and release the lock.
- The player: every control reachable, and the transcript's cues are focusable
  and activate with Enter and Space.

### 3.3 A screen reader on the lesson page

The densest surface and the only dynamic route, so `verify:a11y` has never seen
it. NVDA with Firefox, or VoiceOver with Safari.

- The page announces its title once, not twice.
- The transcript announces as a list with a count, and a cue's active state is
  perceivable without colour.
- Progress is announced as a value, not as decoration — the `<progress>` element
  carries this natively, which is why it is a `<progress>` and not a styled
  `<div>`.
- A refusal (`LessonGate`) is announced when it replaces the player. Sign out in
  another tab and reload to reach one.
- **Cue changes must not flood.** If the transcript announces on every cue the
  page is unusable; that is a finding even though no criterion names it.
- **The transcript announces in the language it is written in** — added
  2026-10-03 with the `lang` fix. Spanish cues read with a Spanish voice, not an
  English one mangling them. This is the only check here that no automated tool
  can perform: axe cannot know "Hola, buenos días" is not English, which is why
  twenty-six passing tests and an axe run sat on top of the fault.

### 3.3a Time-based media — **unexamined, added 2026-10-03**

**Nothing in this section has been done.** It exists because ADR-030 §2a found that
the whole of WCAG 1.2 was never assessed, in a product whose content is video.

**It cannot be performed until a real lesson exists.** Every check below needs
footage to look at, and `MediaAsset` rows exist only in test fixtures. Do not mark
these "pass" against a fixture — a fixture has no visual content to describe, so it
passes everything vacuously.

At the first real lesson upload, for that lesson:

- **1.2.2 Captions (A).** Watch with the captions track on and the sound off. Does
  it carry non-speech audio and identify speakers, or is it a speech transcript
  wearing `kind="captions"`? The source is Deepgram output, so expect the latter.
- **1.2.1 Audio-only (A).** For a `LessonType.AUDIO` lesson: is the transcript
  presented as an alternative to the audio, or only as a reading aid alongside it?
- **1.2.3 / 1.2.5 Audio description (A / AA).** Watch with the screen off. Note
  every piece of teaching that did not survive. **Pronunciation lessons showing
  mouth position are the expected failure** — their content is visual by design.

A finding here has a per-lesson production cost and is therefore a §5 approval
matter, not something to fix in code. Record it under §4 and stop.

### 3.4 Zoom, reflow, and text expansion

**2026-10-17 native page-zoom check:** isolated Chrome 155.0.8059.80 on Windows;
native Appearance → Page zoom set to 200%. Viewport width changed 1422→711 CSS px
and DPR 1→2; direct Chrome metrics also reported `zoom: 2`. Twelve routes passed
in both light/dark preferences (24 cases, 258 keyboard stops), including synthetic
form refusals, empty My Courses and long lesson/transcript content. No measured
overflow, clipped headings/controls, obscured focus or runtime errors. Evidence:
`native-zoom-review.json`, `native-zoom-metrics.json`, `native-zoom-confirm-*.png`
in the task visualization directory. This is a bounded automated Chrome check;
native text-only zoom, other engines and human assistive-technology checks remain open.

- **200% zoom** (1.4.4) on every route: no loss of content or function.
- **320 CSS px wide** (1.4.10): no horizontal scrolling, no two-dimensional
  scroll. The lesson layout is two columns at `lg` and must collapse.
- **Text-only 200%** where the browser supports it, which is where a fixed-height
  container clips.
- Simulate expansion by lengthening the longest strings you can find — a course
  title, a refusal message. ADR-033 notes German and Arabic both run longer than
  English, and no localisation exists yet, so this is the cheap proxy.

### 3.5 Forced colours — **all three checks passed 2026-09-28**

**2026-10-17 browser-furniture evidence:** isolated Chrome 155 native transcript
scrollbars were captured in light/dark; genuine email autofill was captured in
both preferences, with 18.33:1 contrast. See STATUS and ADR-032. Password-manager
autofill, other engines and human confirmation remain open; no conformance claim.

**2026-10-18 limit:** the isolated headless password manager's import control did
not open a file chooser. Password-manager autofill remains unverified; use an
interactive browser. The successful email-address autofill pass does not cover it.

**2026-10-18 follow-up supersedes that limit for saved-password testing:** Chrome's
Add password dialog worked. Both inputs matched `:autofill`; intercepted submissions
matched the synthetic saved login in both preferences, with values retained and
submission enabled after refusal. See `test-saved-password-binding.cjs` and its JSON.
Eight learner recovery/gate cases also passed at 1440px light and 320px dark, with
zero axe violations. Human screen-reader/device checks and real media remain open.

Windows High Contrast, or Chrome DevTools → Rendering → `forced-colors: active`.

- ~~Focus is still visible.~~ **Confirmed by the owner 2026-09-28.** This is the one
  that broke once already: Tailwind 4 renamed `outline-none`, the drawer and `<main>`
  kept the old spelling, and the transparent outline a high-contrast mode turns
  visible was replaced by no outline at all. `outline-hidden` restored it, and the
  fix has now been seen holding in a real high-contrast mode — which is the only way
  it could be, since the difference between the two spellings is invisible everywhere
  else.
- ~~`Notice` remains distinguishable~~ — **confirmed.** Its symbol carries the
  meaning when the background colour is overridden, which is why it has one.
- ~~The current-page state in the navigation survives.~~ **Confirmed.** It must not
  rest on colour alone; `aria-current="page"` is what a screen reader uses, and a
  visual indicator is what everyone else uses.

**Re-check this section after any change to the palette, to `Notice`, or to how the
current page is marked.** It is cheap — three glances — and it is the only check that
can see whether a design survives having its colours taken away.

---

## 4. Recording a finding

In the issue or PR:

1. Criterion number and level.
2. Route, viewport width, and browser or screen reader with versions.
3. What you did, what happened, what should have happened.
4. Whether an automated check *could* have caught it — and if yes, that check is
   part of the fix. ADR-023 §1: a fault that recurs is a fault nobody guarded.

**Do not fix a finding you have not reproduced**, and do not fix one without
first watching a check fail. ADR-006.

---

## 5. Cadence, and being honest about capacity

A full pass is the better part of a day for one person. Proposed, and **not yet
agreed**:

| When | Scope |
|---|---|
| Every PR | The automated column in §1. Already enforced by CI |
| A PR touching the shell, the player, a form, or tokens | §3.2 on the routes it touches, plus §3.5 if tokens moved |
| Before a release | All of §3 |
| After adding a route | §3.2 and §3.4 for that route, plus confirm `verify:a11y` sees it — if it is dynamic, it does not |

The release pass is the one a small team will skip under pressure. **Better to
agree a smaller recurring scope that actually happens** than a thorough one that
is quietly dropped and leaves the runbook claiming a cadence nobody keeps.

---

## 6. What has actually been verified

**2026-10-17 supplement:** Chrome 155.0.8059.80 passed 32 synthetic reflow/text
scenarios across login, registration, forgot/reset password, verification,
Account, My courses and lessons; 342 keyboard stops had no obscured focus after
native scrolling painted. Tested 320px, 720px zoom-equivalent layout and doubled
font/line sizes at 1440px light/390px dark, including long text and error/empty
states. No overflow or tested-control clipping. Screenshots/raw results are in
the task visualization directory (`reflow-review.json`); STATUS records limits.
Actual browser zoom and native text-only zoom still need a person. Historical
notes below do not supersede this narrower automated evidence.

**Public-page supplement, 2026-10-17:** the same four modes passed on homepage,
catalogue, published course detail and pricing: 16 cases, 180 keyboard stops,
no overflow, tested-control clipping or hidden focus. Header hydration completed
before enlargement; public fixed-light theming was preserved. Evidence:
`public-reflow-review.json` and `public-reflow-*.jpg` in the task visualization
directory. This is simulated enlargement/reflow, not actual browser zoom.

**§3.1 only.** Nothing else in §3 has been walked, and until a row appears for a
section, nothing in this file may be cited as evidence about it.

| Date | Section | By | Result |
|---|---|---|---|
| 2026-09-28 | §3.1, hero | Owner, Firefox | **Headline shows with reduced motion on.** The half that proves the hydration fix: the mismatch is what left `opacity: 0` stuck inline, so a visible headline means server and client agree. Version not recorded |
| 2026-09-28 | §3.1, below the fold | Owner, Firefox | **Course cards and all four panels show on scroll.** The other mechanism — `Reveal` and `StaggerList`, driven by `whileInView` and an `IntersectionObserver`. Checked on a production build served from the host, because the compose `web` container was returning 500s |
| 2026-09-28 | §3.2, 2.4.11 only | Owner | **Found a failure:** the focus ring sat behind the fixed "Site map" button. Reproduced at 420×480 on `/courses` — the course card's link and both footer links overlapped it — and fixed. Re-measured at zero overlaps. **The rest of §3.2 was not walked** |
| 2026-09-28 | §3.5, focus ring | Owner | **Focus ring still visible in forced colours.** Confirms the `outline-hidden` fix held — the difference between that and `outline-none` is invisible outside a high-contrast mode, so this could not have been checked any other way |
| 2026-09-28 | §3.5, the other two | Owner | **`Notice` stays distinguishable and the current-page state survives.** §3.5 is complete. ADR-029's palette was described in ADR-030 §4 as something that "cannot be reasoned about" under forced colours — it has now been looked at instead, and it holds |

**§3.1 is closed.** The landing page renders for a reduced-motion visitor, both the
mount path and the scroll-triggered path. That was the bug that started this
workstream — the page was **entirely blank** for exactly the people who had asked
for less motion — and it is now the one thing here confirmed by a person rather
than argued from a passing test.

**§3.2 is the interesting one to finish.** Its 2.4.11 check found the only real
WCAG 2.2 failure in the product, and that is now fixed — but the rest of the
keyboard pass (focus visible at every stop, the drawer's trap and restoration, the
player's controls, the transcript's cues) has not been walked. A criterion that
turned up one fault is worth completing.

**Also outstanding:** the screen-reader pass (§3.3) and zoom and reflow (§3.4).

**§3.3a is outstanding in a different way, and worse.** The others are checks nobody
has got to. Time-based media is a set of criteria nobody had *written down* until
2026-10-03 — the whole of WCAG 1.2, in a video product, absent from this runbook and
from ADR-030. It cannot be walked yet, because there is no lesson footage to walk it
against, and that is exactly why it had to be recorded rather than left to surface at
a launch review. See ADR-030 §2a.

**Not §3.5 — that one is done**, and this line said otherwise until 2026-09-28. The
table above records all three of its checks passing; the sentence had been written
when none of them had. Worth noting rather than quietly editing: a runbook whose
summary disagrees with its own evidence table is the failure mode this section
exists to prevent.

**And one route has never been walked at all:** `/verify-email`, added 2026-09-28.
`verify:a11y` sees it and axe covers its three states, which is the automated column
only — the §3.2 keyboard order across its two forms and the §3.4 reflow pass are both
outstanding, per the cadence table's "after adding a route" row.
