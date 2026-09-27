# ADR-032 — The theme follows the system, and `color-scheme` is missing

**Status:** proposed
**Date:** 2026-09-27
**Decides:** whether the product gets a manual theme control, and one defect
found while asking
**Depends on:** ADR-024 (the public catalogue stays static), ADR-029 (visual
refresh: semantic light/dark tokens), CLAUDE.md invariant 9 and invariant 15

---

## Decision

**Keep following the operating system. Do not add a manual toggle.**

And fix the thing found while looking: **`color-scheme` is never declared**, so
in dark mode the browser still renders native controls, scrollbars and form
widgets from the light palette against `#171827` surfaces.

That second part is not a preference. It is a one-line defect with a visible
consequence, and it is the reason this ADR is worth writing rather than leaving
the status quo undocumented.

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

## 2. The defect: `color-scheme`

Grep the stylesheet: `color-scheme` appears nowhere. Only the media query does.

`color-scheme` is what tells the browser which palette to use for the parts of
the page **the stylesheet does not control** — the scrollbar, the default border
and background of an `<input>` before our classes apply, a `<select>`'s dropdown,
the spin buttons on a number input, the native video controls' chrome, and the
form-autofill background.

Without it, a dark-mode visitor gets our dark surfaces with light-mode browser
furniture. The most likely places it shows in this product:

- **Scrollbars** on the transcript panel (`overflow-y-auto`) and the mobile
  drawer, both of which scroll inside a dark surface.
- **Autofill** on the auth forms. Browsers paint a light yellow or blue fill over
  an autofilled field, computed against the assumed light scheme, which can drop
  the text below the contrast `contrast.test.ts` just certified.
- **Native video controls**, which is the one surface in the product where a
  learner spends most of their time.

The fix is one declaration on `:root`, keyed to the same media query that already
switches the palette, or the two-value form so the browser knows both are
supported.

**Not verified in a browser.** The reasoning is from the CSS specification's
purpose for the property, not from an observation — the effects are
browser-specific and some are platform-specific. Whoever implements this should
look at a dark-mode scrollbar before and after, and at an autofilled login field,
because that is the kind of claim this project does not accept on argument alone.

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

1. A dark-mode scrollbar on the transcript panel and an autofilled login field,
   looked at before and after. §2 is reasoning, not an observation, and must not
   ship as one.
2. `contrast.test.ts` still passes both schemes.
3. A test asserting `color-scheme` is declared — cheap, and it is exactly the kind
   of one-line declaration a later reformat drops silently.

## Related

ADR-024, ADR-029, ADR-030, `docs/design-system.md` §1 and §7,
`docs/runbooks/accessibility-verification.md` §3.5.

**Approval required:** the owner, because §3 declines a feature a user might
reasonably expect. §2 is a defect fix and needs no product decision.
