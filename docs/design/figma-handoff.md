# Figma structure — a written handoff

**Status:** proposed structure. **No Figma file has been created or modified.**
**Last updated:** 2026-10-31 — audited against the code and found to be describing a
system two changes out of date. See "What this file had missed" below.
**Governed by:** ADR-029 (visual direction), ADR-030 (accessibility),
ADR-032 (theme), ADR-037 (homepage art direction), `docs/design-system.md`

This describes how a Figma file *should* be organised so that it and the code stay
in agreement. It is a recommendation for whoever opens Figma, not a record of work
done.

**One direction of truth: the code is ahead.** The design system already exists,
is tested, and ships. So this file is mostly about **mirroring** what
`globals.css` and `src/components/ui/` already say — not about designing something
Figma then hands to engineering. Getting that backwards is how a Figma file
becomes a museum of screens nobody built.

ADR-029 names Linglee as the visual reference and is explicit that its likes are
"not evidence of usability or permission to reuse its assets". **Inspiration, not
assets.**

## What this file had missed — audited 2026-10-31

**It predated ADR-037 completely** — that ADR was referenced nowhere and the word
`editorial` appeared zero times, while the code had already shipped both halves of
it. A designer building from the old §2 and §3 would have produced:

- **two colour modes when there are three**, missing the one the public pages and
  sign-in actually use — the first thing a visitor sees;
- **`radius` 8/12/20 everywhere**, when the editorial surface is 3/4/8, so every
  public-page corner would have been wrong;
- a sans display face, when the editorial surface is a serif stack;
- **three `PageTitle` variants when there are four.**

It also never listed `LoadFailure`, added with the failed-load work. "Six
primitives" was seven.

**The pattern worth noting rather than the individual misses.** This file says "the
code is ahead… this is mostly about mirroring". That is the right relationship and
it is also why the file rots silently: nothing fails when the mirror stops matching.
`verify:css` cannot catch it — it checks that token references *resolve*, not that a
prose document still describes them. §10 asks for the two to be kept in agreement
and is the only control, which makes it a convention rather than a control.

**`LoadFailure` is undocumented in `docs/design-system.md` too.** Recorded here, not
fixed here — that file is the primitives' own reference and the gap belongs to it.

---

## 1. Pages

One Figma page per row. Flat, because a small team loses things in nested
sections.

| Page | Holds |
|---|---|
| **00 · Read me** | What this file is, who owns it, the link to `docs/design-system.md`, and the rule that code is authoritative for tokens |
| **01 · Foundations** | Colour, type, spacing, radii, elevation — as variables, not swatches |
| **02 · Components** | Component sets for the six primitives, with variants |
| **03 · Patterns** | Shell, navigation, drawer, card, form, notice, empty and error states |
| **04 · Public catalogue** | Landing, `/courses`, course detail, `/pricing` |
| **05 · Authentication** | Four flows, every state |
| **06 · Learner** | `/my-courses`, lesson player, transcript |
| **07 · Moderation** | Only if and when a custom surface is approved — see §8 |
| **08 · Accessibility notes** | Annotations, focus order, announcements |
| **09 · Prototypes** | Two flows, no more — see §9 |

---

## 2. Tokens → variables

Create a variable collection **`tokens`** and mirror `globals.css` exactly. Names
match the CSS custom properties minus the `--color-` prefix, so a conversation
about `surface-sunken` means one thing in both places.

**Three modes in one collection: `light`, `dark` and `editorial`.** This is the
whole reason to use variables rather than styles — one component, three modes, no
duplicated frames.

**`editorial` is not an afterthought; it is what a visitor sees first.** ADR-037
scopes it with `[data-site-style="editorial"]` to the public pages and sign-in, and
it pins `color-scheme: light` so it does **not** follow the OS preference — the
learner surface and the other authentication palettes stay untouched. Treat it as a
sibling mode, not a variant of light:

| What changes | `light` | `editorial` |
|---|---|---|
| `paper`, `surface` | app values | `#faf7f0` — warm, not white |
| `surface-sunken` | app value | `#f0ece3` |
| `accent` | `#4945a5` | `#4541b5` |
| `accent-hover` | app value | `#343087` |
| `brand-coral` | app value | `#c44656` |
| `--font-display` | sans stack | **serif stack** (`ui-serif, Georgia, …`) |
| `radius` sm/md/lg | 8 / 12 / 20 | **3 / 4 / 8** |

All seventeen colour tokens are overridden, plus the display font and all three
radii. **A mockup using 8/12/20 corners on a public page is wrong by 5–12px per
corner** — the single most visible way to get this surface wrong.

| Group | Variables |
|---|---|
| `ink` | `ink`, `ink-muted`, `ink-subtle` |
| `surface` | `paper`, `surface`, `surface-sunken` |
| `line` | `line`, `line-strong` |
| `accent` | `accent`, `accent-hover`, `accent-subtle`, `on-accent` |
| `brand` | `brand-coral` |
| `status` | `danger`, `danger-subtle`, `success`, `success-subtle` |
| `radius` | `sm` 8, `md` 12, `lg` 20 — **but 3 / 4 / 8 in `editorial`** |
| `shadow` | `sm`, `md` — as effect styles, since Figma variables do not carry shadows |

**Do not invent a numeric colour ramp.** There is no `indigo-600` in this system;
there is `accent`. A ramp in Figma that the code does not have produces mockups
that cannot be built.

**Dark mode is not a tint of light mode.** `accent` goes from `#4945a5` to
`#b5b0ff` and `on-accent` from white to `#20203b` — they invert relationship, not
just lightness. Copy the values; do not derive them.

**Contrast is already enforced in code.** `contrast.test.ts` computes WCAG ratios
for both schemes from these values. If a designer proposes a new colour, the test
is the acceptance gate, and it will object before a pull request does.

### Type

One family. `--font-display` for headings, a system stack for body. **Do not set a
web font in Figma** — the app deliberately loads none, and a mockup in Inter is a
mockup of a product that does not exist. Use the closest system face available and
annotate that the rendered face varies by platform, which is the trade the code
accepted.

Text styles, matching `PAGE_TITLE` and nothing more:

| Style | Value | Maps to |
|---|---|---|
| `title/page` | display, 36px, tight leading and tracking | `PageTitle` default |
| `title/interstitial` | display, 30px, tight | `PageTitle variant="interstitial"` |
| `title/section` | display, 24px | `PAGE_TITLE.section` — **open question, see design-system §3** |
| `heading/2` | display, 24px | Hand-written `<h2>` |
| `body`, `body/muted`, `body/small` | system stack | `ink`, `ink-muted`, and 14px |

---

## 3. Components → component sets

Seven primitives — this said six and predated `LoadFailure`. Variant properties
named exactly as the code's props, so a handoff conversation needs no translation.

### `Button` — the one that needs care

Properties: `variant` (primary · secondary · ghost) × `size` (lg · md · sm) ×
`lift` (true · false) × `state` (rest · hover · focus · pressed · disabled ·
pending).

That is a large matrix. **Do not enumerate all of it.** Build `variant` × `size`,
and show `state` only for `primary/md` plus whatever a specific screen needs —
the states are systematic and documented; drawing 108 frames is maintenance with
no reader.

Two mechanical facts the Figma component must reproduce or it will mislead:

- **Every variant has a border**, transparent except on `secondary`. Without it a
  bordered button is 2px taller than the one beside it — which is exactly the bug
  that sent the landing page's two calls to action out by 2px.
- **`lg` is 16px text, `md` and `sm` are smaller.** The size carries the type
  size; do not set type separately.

> **Open:** whether `<button>` should lift on hover as the calls to action do. Do
> not settle it in Figma. `docs/design-system.md` §4 has the recommendation.

### The rest

| Component | Variant properties | Notes |
|---|---|---|
| `Card` | `hoverable` (true · false) | Hover lifts by 2px with a spring, and the shadow moves `sm` → `md` |
| `Field` | `state` (rest · focus · error · disabled), `hint` (true · false), `optional` (true · false) | **Marks optional, not required** — the common case carries no badge |
| `Notice` | `tone` (error · success), `title` (true · false) | Must include the symbol. Colour is never the only indicator |
| `Badge` | `tone` if more than one exists in code | Non-interactive |
| `PageTitle` | `variant` (page · **editorial** · interstitial · section) | Text styles from §2. `editorial` is the homepage only, accepted in ADR-037 after the original scale |
| `LoadFailure` | `retrying` (true · false) | A failed load **with a way out**. Added after four failed-load states dispensed advice and offered no retry. The retry control sits **outside** the live region, or a screen reader announces the button as part of the error |

**Auto Layout everywhere, and no fixed heights on anything containing text.** A
fixed height is how a mockup hides text expansion, which §7 is about.

---

## 4. Patterns and layout

`SiteShell` is shared by the public and learner surfaces (ADR-026 §4), so build it
**once** as a component with a content slot.

Breakpoints to draw, matching the Tailwind defaults in use:

| Name | Width | Why this one |
|---|---|---|
| `xs` | **320** | WCAG 2.2 reflow (1.4.10). The narrowest supported, and the one people skip |
| `sm` | 640 | Where the CTA row goes horizontal |
| `lg` | 1024 | Where the lesson layout becomes two columns |
| `xl` | 1280 | **Where the navigation rail replaces the mobile drawer** |

`xl` matters more than it looks: the drawer and its floating toggle are
`xl:hidden`, so `lg` and `xl` are genuinely different navigation designs, not one
design at two sizes.

**Keep responsive variants beside their component**, not on a separate "mobile"
page. A phone layout parked elsewhere is a layout that stops matching.

---

## 5. Screens worth drawing, and states that are usually forgotten

Draw the **states**, not just the happy screen. Every one below exists in code and
each has been the source of a real bug.

**Public catalogue** — landing; `/courses` with results, with a filter applied, and
**with no results**; course detail with and without the personal progress strip
(it renders nothing for anonymous visitors, by design); `/pricing` in its
**unannounced state**, because `PRICE_BOOK` is `null` and no price may be shown
until the payment decision is made.

**Authentication** — each of the four pages at rest, pending, with a field error,
with a page-level refusal, and in its confirmation state. The confirmations are
deliberately conditional: "if this address can be registered…", never "we have
emailed you". **Do not redraw them as a confident success message** — that wording
is an anti-enumeration control with tests behind it.

**Learner** — `/my-courses` loading, empty ("you have not started a course yet"),
populated, and finished; the lesson player with the transcript; and **each
entitlement refusal**, of which there are six with typed messages, one of which
(`GRACE_PERIOD_ENDED`) deliberately has no action link.

**Boundaries** — the error and loading pages ADR-031 proposes. Plain by design.

---

## 6. Accessibility annotations

On page 08, and referenced from each screen:

- **Focus order** as a numbered overlay for the shell, the drawer, and any form.
- **Focus ring**: 2px `accent` at 2px offset, drawn as an effect so it is visible
  in mockups rather than implied.
- **The 2.4.11 risk**: annotate the floating "Site map" button below `xl` as a
  known overlap hazard with focused content at the foot of a page (ADR-030 §3).
- **Announcements**: which regions are live and how politely. Loading regions are
  `polite`; a `Notice` error is `assertive`.
- **Reduced motion**: mark every animated element with what it does when motion is
  reduced. Transforms stop; opacity persists.
- **Target size**: 24×24 minimum (2.5.8). Annotate anything close.

---

## 7. Text expansion and direction

No localisation is approved (ADR-033). Two cheap habits so Figma does not
encode an English-only assumption:

- **Draw the longest realistic string**, not "Course title". German and Arabic both
  run longer than English; a component sized to a short label breaks on the first
  real one.
- **Use Auto Layout with hug or fill, never fixed width**, on anything holding a
  translated string.

**Do not build RTL variants.** No locale is approved, and speculative mirrored
frames are maintenance for a decision nobody has taken. Annotate instead that
logical properties are preferred in code so mirroring is cheap later.

---

## 8. Instructor and moderation — probably nothing to draw

The instructor API exists and **has no caller** (ADR-026). Administration runs
through the Django admin (ADR-018, ADR-019).

**Do not design an instructor dashboard.** Deciding a workflow belongs in a custom
Next.js surface rather than the Django admin is an architectural decision that
needs its own ADR, and a Figma file full of screens for it would be an argument
for building something nobody approved.

Page 07 stays empty until that decision exists. Upload progress feedback is the
most likely first candidate, because direct-to-R2 upload is the one place the
Django admin genuinely cannot help.

---

## 9. Prototypes — two, deliberately

Prototypes rot faster than anything else in a Figma file.

1. **Mobile navigation**: open the drawer, tab through it, Escape, focus returns
   to the toggle. This is the one worth having, because it is a behaviour with
   three tests behind it and a prototype communicates it faster than prose.
2. **A learner hits a paywall**: lesson → refusal → where it points. Worth having
   because the refusal copy is a product decision and needs to be read in context.

Everything else: annotate, do not prototype.

---

## 10. Keeping the two in agreement

| If this changes | Then |
|---|---|
| A token value in `globals.css` | Update the Figma variable. `contrast.test.ts` is the gate; Figma follows |
| A component variant in a `cva` config | Update the component set's variant property to match the prop name |
| A new primitive | It exists in code first — one caller is a component, two unrelated callers make a primitive |
| A Figma-only colour or type style appears | It is a proposal, not a token. Raise it as one |

**Review rule:** a mockup using a value that is not a variable is not ready for
implementation. That single rule prevents most drift, and it is cheaper than a
sync tool.

**No plugin, no token-sync service, no design-system SaaS is proposed.** Each
would be a dependency and a cost, and this system is 17 colours, 3 radii and 2
shadows — small enough that a person copying values is both cheaper and less
likely to break.
