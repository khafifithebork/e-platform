# Runbook — verifying accessibility

**Status: written; §3.1 passed and §3.2's 2.4.11 check done, both 2026-09-28.**
Written 2026-09-27 alongside ADR-030. The owner confirmed §3.1 in full and found the
2.4.11 fault in §3.2, which has since been fixed. **The rest of §3.2, and §3.3 to
§3.5, have not been walked.** See §6.

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
`/login`, `/register`, `/forgot-password`, `/my-courses`, a lesson.

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

### 3.4 Zoom, reflow, and text expansion

- **200% zoom** (1.4.4) on every route: no loss of content or function.
- **320 CSS px wide** (1.4.10): no horizontal scrolling, no two-dimensional
  scroll. The lesson layout is two columns at `lg` and must collapse.
- **Text-only 200%** where the browser supports it, which is where a fixed-height
  container clips.
- Simulate expansion by lengthening the longest strings you can find — a course
  title, a refusal message. ADR-033 notes German and Arabic both run longer than
  English, and no localisation exists yet, so this is the cheap proxy.

### 3.5 Forced colours

Windows High Contrast, or Chrome DevTools → Rendering → `forced-colors: active`.

- Focus is still visible. **This is the one that broke once already**: Tailwind 4
  renamed `outline-none`, the drawer and `<main>` kept the old spelling, and the
  transparent outline that a high-contrast mode turns visible was replaced by no
  outline at all. Fixed with `outline-hidden`; check it stayed fixed.
- `Notice` remains distinguishable — its symbol carries the meaning when the
  background colour is overridden, which is why it has one.
- The current-page state in the navigation survives. It must not rest on colour
  alone; `aria-current="page"` is what a screen reader uses, and a visual
  indicator is what everyone else uses.

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

**§3.1 only.** Nothing else in §3 has been walked, and until a row appears for a
section, nothing in this file may be cited as evidence about it.

| Date | Section | By | Result |
|---|---|---|---|
| 2026-09-28 | §3.1, hero | Owner, Firefox | **Headline shows with reduced motion on.** The half that proves the hydration fix: the mismatch is what left `opacity: 0` stuck inline, so a visible headline means server and client agree. Version not recorded |
| 2026-09-28 | §3.1, below the fold | Owner, Firefox | **Course cards and all four panels show on scroll.** The other mechanism — `Reveal` and `StaggerList`, driven by `whileInView` and an `IntersectionObserver`. Checked on a production build served from the host, because the compose `web` container was returning 500s |
| 2026-09-28 | §3.2, 2.4.11 only | Owner | **Found a failure:** the focus ring sat behind the fixed "Site map" button. Reproduced at 420×480 on `/courses` — the course card's link and both footer links overlapped it — and fixed. Re-measured at zero overlaps. **The rest of §3.2 was not walked** |

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

**Also outstanding:** the screen-reader pass (§3.3), zoom and reflow (§3.4), and
forced colours (§3.5).
