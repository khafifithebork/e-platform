# ADR-032 — The theme follows the system, and `color-scheme` was missing

**Status:** accepted by the owner 2026-09-27 (§2 was extracted and fixed the same
day, ahead of the decision on §3)
**Date:** 2026-09-27
**Decides:** whether the product gets a manual theme control, and one defect
found while asking
**Depends on:** ADR-024 (the public catalogue stays static), ADR-029 (visual
refresh: semantic light/dark tokens), CLAUDE.md invariant 9 and invariant 15

---

## Decision

**Keep following the operating system. Do not add a manual toggle.** — *accepted
by the owner 2026-09-27.*

And the thing found while looking: **`color-scheme` was never declared**, so in
dark mode the browser rendered its own furniture — scrollbars, autofill, native
video controls — from the light palette against `#171827` surfaces. **Fixed
2026-09-27**, split out of this ADR at the owner's instruction because a defect
with no product question attached should not wait behind one that has.

Splitting them meant the fix shipped a few hours before the decision, which was
the point: §2 was never waiting on anything. §2 also had a claim in it that
measurement disproved — see "What measurement corrected".

---

## 1. What exists

`src/app/globals.css` defines the palette in `@theme` and redefines a subset
inside `@media (prefers-color-scheme: dark)`. That is the whole mechanism: 17
colour tokens and two shadows, swapped by the media query.

**It works, and it works well.** No component contains a single conditional about
the theme. `contrast.test.ts` computes WCAG ratios for both schemes from these
values, so a palette tweak that breaks dark mode fails the suite. ADR-029
accepted this shape and nothing about it needs revisiting.

**No ADR records the decision**, though — so "we chose to follow the system" is
indistinguishable from "nobody got round to a toggle". This file is the
difference.

---

## 2. The defect: `color-scheme` — **extracted and fixed 2026-09-27**

**Split out of this ADR at the owner's instruction**, because it was a defect with
no product question attached while the rest of this file was a product decision
then still open. Fixed in `globals.css` with
`:root { color-scheme: light dark; }` and pinned by `src/app/theme.test.ts`.

`color-scheme` tells the browser which palette to use for the parts of the page
**the stylesheet does not control**. Without it, a dark-mode visitor gets our dark
surfaces with light-mode browser furniture.

`light dark` rather than a value per media query: it declares support for both and
lets the browser follow the visitor's own preference, which is the system-only
behaviour this ADR keeps. A single value would override that choice.

### What measurement corrected

This section originally listed "the default border and background of an `<input>`
before our classes apply" and "the spin buttons on a number input" among the
things affected, and was labelled as reasoning from the specification rather than
an observation. **The observation contradicted it.**

Measured in a browser with dark-scheme emulation, comparing a bare `<input>`,
`<select>` and `<textarea>` inheriting `color-scheme: light dark` against the same
three forced to `light`: **computed background, colour and border were identical
in both cases.** Tailwind's Preflight already resets form controls to a
transparent background and inherited colour, so the user-agent styling this ADR
expected to change was never in play for those elements.

So the claim was wrong for this codebase, and the honest list of what the
declaration actually governs here is shorter:

| Affected | Observable in the agent's browser? |
|---|---|
| Scrollbars — the transcript panel and the mobile drawer both scroll inside a dark surface | **No.** A scrollbar's colours are not exposed to `getComputedStyle` |
| Autofill background, on the auth forms | **No.** Requires a real autofill interaction |
| Native video controls — where a learner spends most of their time | **No.** Needs a configured provider |
| A `<select>`'s dropdown popup, and date and time pickers | **No.** Rendered by the platform, outside the document |

**What is verified:** the declaration is live — `getComputedStyle(document.documentElement).colorScheme`
returns `light dark`, with `prefers-color-scheme: dark` matching and the dark
tokens active (`--color-ink: #f1f2fc`, `--color-paper: #171827`), checked against a
`rounded-full` control so an unloaded stylesheet could not be mistaken for a
result.

**What is not:** every item in the table. The fix is correct by specification and
the wrong list has been removed, but **nobody has yet looked at a dark-mode
scrollbar or an autofilled field.** That remains item A4 in
`docs/specs/frontend-roadmap.md` and §3.5 of the accessibility runbook. The
autofill case is the one that matters most, because a browser-painted background
can drop text below the 4.5:1 `contrast.test.ts` certifies — and that test cannot
see a background the browser painted.

---

## 3. Why no manual toggle

A toggle is not hard; it is *not free*, and nothing has asked for it.

| Cost | Detail |
|---|---|
| **A blocking script** | The public routes are statically generated (ADR-024, invariant 15). One HTML file serves everyone, so a stored preference can only be applied in the browser. Applied after hydration, the visitor sees a flash of the wrong theme on every load. Avoiding that needs an inline script in `<head>` that runs before first paint — the one place this codebase would have to ship inline JavaScript, and `next.config.ts` keeps `script-src` strict on purpose while allowing `unsafe-inline` for styles only. A nonce would have to be plumbed through |
| **A third state** | A real control has three positions — light, dark, follow system — because two positions cannot express "follow the system", which is the default everyone starts in |
| **Storage** | `localStorage` is permitted here; invariant 9 forbids *auth* data in storage, and a theme is not that. But it is per-device, so it will disagree with the same person's other device, and there is no user-preferences endpoint |
| **A control in the shell** | Header space ADR-029 allocated to navigation and the account menu |
| **Two more test paths** | Every theme-sensitive assertion doubles once the theme can disagree with the system |

Against that: no owner request, no user request, and the operating system already
carries the preference — which is where most people set it once and expect
everything to obey.

**The honest summary: following the system is not a limitation here, it is the
correct default.** A toggle is what you add when you have evidence people want to
override it.

---

## 4. Alternatives

| Option | Why not now |
|---|---|
| **Toggle with a pre-paint inline script** | The complete answer. Costs the CSP work in §3 and a control nobody has asked for. Revisit on a real request |
| **Toggle without the script, accepting a flash** | The flash is on a statically generated marketing page — the first impression. Worse than no toggle |
| **CSS-only toggle (`:has()` on a checkbox)** | No JavaScript and no flash, but it cannot persist across navigations, which makes it a demo rather than a preference |
| **A `dark:` variant strategy instead of token redefinition** | Would mean touching every component and `contrast.test.ts`, to arrive at the same rendering. ADR-029's approach is better and already works |

---

## Consequences

**Positive.** One mechanism, no conditionals in components, both schemes
contrast-checked by a test. Declaring `color-scheme` fixes a real visual defect
for every dark-mode visitor for one line. The decision to *not* build a toggle is
now a decision rather than an omission.

**Negative.** Somebody who wants the app light while their system is dark cannot
have it, and that is a legitimate preference we are declining. Anyone adding a
toggle later inherits the CSP work in §3 — this ADR does not make that cheaper,
it only makes the cost visible in advance.

**UX and responsive.** None beyond §2's browser furniture. No layout effect.

**Accessibility.** The autofill case in §2 is the accessibility-relevant one: it
can push a form field's text below the 4.5:1 that `contrast.test.ts` certifies
for our own colours, and the test cannot see a browser-painted background. Add it
to the human pass in `docs/runbooks/accessibility-verification.md` §3.5.

**Security.** Declining the toggle avoids introducing an inline script and the
nonce plumbing that a strict `script-src` would need. Worth stating: that is a
side benefit, not the reason.

**Performance.** Nothing. One declaration, no JavaScript, no request.

---

## Implementation guidance

- Declare `color-scheme` on `:root` in `globals.css`, next to the media query so
  the two cannot drift apart.
- Do not add `dark:` variants to components. The tokens handle it.
- If a toggle is ever approved, it supersedes this ADR explicitly — it does not
  arrive as an unreviewed pull request, because the inline-script and CSP part is
  a security-relevant change.

## Verification criteria

1. ~~A test asserting `color-scheme` is declared.~~ **Done** — `src/app/theme.test.ts`,
   five assertions, each provoked: removing the declaration fails three, forcing a
   single scheme fails one, and adding a `data-theme` selector fails the one that
   pins this ADR's no-toggle decision.
2. ~~`contrast.test.ts` still passes both schemes.~~ **Done.**
3. **Outstanding:** a dark-mode scrollbar and an autofilled login field, looked at
   by a person. Roadmap A4. Neither is observable in the agent's browser, and §2
   now says so rather than implying the fix was seen working end to end.

## Related

ADR-024, ADR-029, ADR-030, `docs/design-system.md` §1 and §7,
`docs/runbooks/accessibility-verification.md` §3.5.

**Approval:** granted by the owner on 2026-09-27, declining the toggle. §2 had
already been split out and fixed the same day.

**What this closes and what it does not.** The theme mechanism is settled: one
media query, semantic tokens, no toggle, no stored preference, and a test that
fails if a `data-theme` selector appears. It does **not** close roadmap A4 — nobody
has yet looked at a dark-mode scrollbar or an autofilled field, and §2 says so.
Declining the toggle also does not forbid one forever: a real user request
supersedes this ADR explicitly, and §3 records the cost so that conversation starts
from a number rather than an impression.
