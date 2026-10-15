# The design system

**Status:** reference documentation, not a decision record
**Last updated:** 2026-10-15
**Governed by:** ADR-029 (visual refresh), ADR-030 (WCAG 2.2 AA),
ADR-032 (application theme), ADR-037 (public editorial extension), CLAUDE.md §4 invariants and §13 style

This describes what the frontend **already has**, so it can be used
consistently. It records no new decisions. Where a genuine decision is open, it
is marked **OPEN** and points at who must settle it — this file must not be used
to settle one by being edited.

Nothing here is a substitute for `CLAUDE.md`. Where the two appear to differ, the
brief wins and this file is wrong.

---

## 1. Tokens

Defined once, in `src/app/globals.css`, inside `@theme`. The dark scheme
redefines a subset inside `@media (prefers-color-scheme: dark)`. Tailwind 4
generates a utility for every one. Public routes and sign-in override these
properties under `[data-site-style="editorial"]`; learner and other
authentication defaults remain intact.

**Semantic names only.** There is no `--color-indigo-600`. A component asks for
`accent` and gets whatever the current scheme says that is, which is what makes
one palette serve both schemes without a single conditional in a component.

### Colour

| Token | Use |
|---|---|
| `ink`, `ink-muted`, `ink-subtle` | Body text, secondary text, and the quietest text that must still pass contrast |
| `paper` | The page: body default and the full-height `SiteShell` surface |
| `surface`, `surface-sunken` | A raised card, and a recessed panel or well |
| `line`, `line-strong` | A divider, and a border that must be *seen* — an input, a secondary button |
| `accent`, `accent-hover`, `accent-subtle`, `on-accent` | Actions. `on-accent` is text on an accent fill and is defined separately from `ink` on purpose: it is not the same colour in either scheme |
| `brand-coral` | **The restrained brand detail ADR-029 asks for.** Used once, on the logo mark |
| `danger`, `danger-subtle`, `success`, `success-subtle` | `Notice` tones, field errors, the finished state |

**Contrast is computed, not eyeballed.** `src/app/contrast.test.ts` reads these
values and asserts WCAG ratios for **both** schemes. Changing a hex value means
running the suite; a palette that passes in light and fails in dark fails for
everyone with dark mode on, which on a reading surface is a lot of people.

### Editorial overrides — public routes and sign-in

The homepage, catalogue, pricing and sign-in inherit a fixed light palette from
their editorial shell (ADR-037). Paper and surface are warm ivory (`#faf7f0`), with
a recessed surface (`#f0ece3`); ink is near-black (`#191919`), muted text
`#50505a`, and subtle text `#5b5963`. Indigo actions use `#4541b5`, deepen to
`#343087` on hover, and use white on the fill; the subtle accent is `#eeebfa`.
Rules use `#d1ccc3`, with `#817b72` for stronger borders. Selection uses the
accent and on-accent pair. These are scoped semantic overrides, not replacement
tokens for learner or other authentication screens. Sign-in reuses these
existing overrides without adding or changing tokens.

### Type

Operating screens use `--font-display` for headings, and `body` sets a system
stack for everything else. Public pages and sign-in override `--font-display` with
`ui-serif, Georgia, Cambria, "Times New Roman", serif`; the homepage also uses
serif for its editorial title and supporting description (ADR-037). This is a
scoped implementation constraint, not a new global display-face rule. Sign-in
uses the serif face for its bold 30px wordmark and 30px interstitial heading;
supporting copy, field labels, inputs, buttons and links retain the body sans.
**No web font is loaded** — `src/app/layout.tsx` explains why at
length, and the short version is that a build which cannot reach a font service
silently ships a fallback, so the font you tested is not the font you shipped. A
licensed face, if one is ever chosen, is self-hosted with `next/font/local`.

Page titles are not chosen per page. See §3.

### Radii, shadow, elevation

`--radius-sm: 8px` · `--radius-md: 12px` · `--radius-lg: 20px`
`--shadow-sm` · `--shadow-md`, plus `--shadow-card-resting` and
`--shadow-card-hovered` as aliases so a card's two states are named rather than
guessed at each call site.

Elevation is two steps, not a scale. `sm` for a control or a panel at rest, `md`
for something lifted — a hovered card, an overlay. **Dark mode redefines both**
with higher alpha, because a shadow tuned for white does nothing on `#171827`.

The editorial shells override radii to 3px / 4px / 8px and use gentler ink shadows:
`sm` is `0 2px 4px rgb(25 25 25 / 0.04)`, `md` is
`0 6px 16px rgb(25 25 25 / 0.08)`. Card aliases still reference these two steps.

### Referencing a token from a class — the one syntax rule

**Always `rounded-(--radius-md)`. Never `rounded-[--radius-md]`.**

Tailwind 4 reads the parenthesis form as `var(--radius-md)` and the bracket form
as the literal string `--radius-md`, which is not a valid value, so the browser
drops the declaration and the style silently never applies. The bracket form is
Tailwind 3's spelling; this project has been on `^4` since its first frontend
commit, so **45 classes across 15 components had never once applied** before this
was found — square corners and missing shadows that no test could see, because
both spellings are valid strings in a `className` and jsdom runs no Tailwind.

Two guards enforce it: `src/test/css-tokens.test.ts` (fast, source) and
`verify:css` (the compiled CSS, catching any property and any spelling).

**A comment counts.** Tailwind's source detection cannot tell prose from code, so
writing the broken form in a `src/` docstring compiles an invalid rule exactly as
a real class would. `globals.css` excludes `*.test.ts(x)` from the scan for this
reason, and that exclusion is load-bearing, not a bundle-size nicety. Worked
examples of the wrong syntax belong in `scripts/` or an excluded test.

**Arbitrary values are still fine.** `h-[36rem]`, `lg:grid-cols-[3fr_2fr]` and
`text-[0.8125rem]` are values, not token references, and the guards ignore them.

---

## 2. Three tiers, and what belongs in each

| Tier | Location | Rule |
|---|---|---|
| **Primitive** | `src/components/ui/` | Knows nothing about this product. No API calls, no domain types, no routes |
| **Composed** | `src/components/site/`, `src/components/motion/` | Shell, navigation, motion. Knows about layout and the app, not about courses |
| **Domain** | `src/components/catalogue/`, `learn/`, `pricing/`, `auth/` | Knows the API types and the product's rules. May fetch |

Two consequences worth stating because they are easy to violate without noticing:

- **A primitive that imports from `@/lib/api` is in the wrong tier.** `Button`,
  `Card`, `Field`, `Notice`, `Badge` and `PageTitle` import nothing but React,
  `cva`/`cn`, and `framer-motion`. Keep it that way; a primitive that knows what
  an `Enrollment` is cannot be reused and cannot be tested without a fixture.
- **Domain components own their own loading, empty and error states.** They are
  the ones that fetch, so they are the ones that know. `MyCourses`,
  `CourseProgress` and `LessonGate` each do this, and ADR-026 explains why
  `CourseProgress` deliberately renders *nothing* in three of its four states.

### Shared logic goes to `src/lib/`, not into a component

When two components need the same rule, the rule moves out. `lib/learn/resume.ts`
exists because `MyCourses` and `CourseProgress` each decided independently where a
learner resumes; `lib/entitlements/denial.ts` is the single refusal table
ADR-026 §3 made a compile-time exhaustive union. **Two copies of a rule is the
shape that drifts quietly, because each copy looks right on its own.**

---

## 3. `PageTitle` — the type scale for page titles

Import `PageTitle`; never write a sized `<h1>`. `PageTitle.test.tsx` fails on any
hand-written `<h1>` anywhere in `src/`, with no exemption list.

| Variant | Size | Use |
|---|---|---|
| `editorial` | 40px; 48px at `sm`; 60px at `xl` | Homepage only: platform serif, balanced wrapping, 1.08 line height, tight tracking |
| `page` *(default)* | `text-4xl` | A destination you navigated to: `/courses`, `/pricing`, a course, `/my-courses` |
| `interstitial` | `text-3xl` | A page standing in for one: an auth form step, a refusal, a 404 |
| `section` | `text-2xl` | `LessonPlayer` only — see **OPEN** below |

**The split is the kind of page, not the column width.** `NotFoundContent` and
`LessonGate`'s refusal use the interstitial treatment; catalogue destinations
use `page`, and the homepage explicitly opts into `editorial`. An
interstitial that titles itself as loudly as the catalogue reads as shouting
about bad news.

The hero uses `PageTitle` directly, producing an ordinary `<h1>` with no entrance
animation. `PAGE_TITLE` remains exported for scale assertions in tests.
The other variant class strings retain their sizes; on public routes and
sign-in their `font-display` resolves to the editorial serif override. Sign-in
keeps `interstitial`; it does not adopt the homepage's `editorial` variant.

> **OPEN — the `section` variant.** It reproduces `LessonPlayer`'s existing title
> byte for byte (`font-display text-2xl text-ink`), which is identical to the
> marketing `<h2>` treatment and sets neither `tracking-tight` nor
> `leading-tight`. Read generously, the video is the subject and the title is a
> label on it. Read unkindly, it predates the scale. **Owner decides.** A test
> pins the string so it cannot drift either way in the meantime.

Section headings (`<h2>`) are still hand-written, and
`(marketing)/typography.test.ts` asserts they share one treatment *within* that
group. Deliberately not app-wide: `MyCourses` titles enrolment cards with an
`<h2>` matching `CourseCard`, which is a card title wearing an `h2` for the
heading outline's sake.

---

## 4. `Button`, and the links that look like buttons

`Button` is a `<button>`: `variant` × `size` × `lift`, plus `pending` and
`pendingLabel`. Use it for anything that acts on the current page.

**A link is not a button.** It needs an `href`, cannot be disabled, and
`whileTap` on a navigation is the wrong gesture. So a link-shaped call to action
imports `buttonStyles` and composes the classes:

```tsx
<Link href="/courses" className={buttonStyles({ variant: "primary", size: "lg", lift: true })}>
```

Sizes: `lg` (`text-base`, for a page's main call to action), `md` (`text-sm`, the
default control), `sm` (inside a card or a dense row).

Two mechanical rules that exist because getting them wrong was invisible:

- **Each size owns its type size; the base sets none.** `buttonStyles` is the raw
  `cva` and does not run `tailwind-merge` the way `Button` does. With `text-sm`
  in the base, `size: "lg"` produced 14px because CSS order decided it — shrinking
  the landing page's calls to action while every test stayed green.
- **The base sets `border border-transparent`, overridden by `secondary`.**
  Without it a bordered variant is 2px taller than an unbordered one beside it,
  and `min-h-*` does not save you: a minimum is a floor, not a cap. Measured both
  ways — the two hero CTAs were 44px and 46px side by side.

> **OPEN — should `<button>` lift on hover?** Today the CTAs raise their shadow
> and `<button>` holds still, preserved through a `lift` variant. That is honest
> about the disagreement and is still two behaviours where a design system wants
> one. **Owner decides.** Recommendation: buttons lift too — the lift is what
> makes a control feel pressable, and the primitive holds still only because
> nobody chose otherwise.

**Never suppress the focus ring.** `Button` carries a comment about this: the
global ring is written at `:where(...)` zero specificity so *any*
`outline-none` on the element wins. If a ring must be visually suppressed on a
large region, use `outline-hidden`, which keeps the `forced-colors` fallback —
`outline-none` in Tailwind 4 does not, and that difference cost the skip-link
target its high-contrast indicator once already.

---

## 5. The other primitives

| Component | Contract |
|---|---|
| `Card` | The one bordered, elevated container. `as` for the tag, `hoverable` for a card that is a link's whole surface. Springs rather than a CSS transition, and only the three tags actually used get a motion component — `motion.create(Tag)` on a runtime tag remounts the node every render |
| `Field` | A labelled input with errors and hint wired for assistive technology: `aria-describedby`, `aria-invalid`, and `role="alert"` on the message because it appears after the user has moved on. Marks *optional* rather than required — the common case carries no badge |
| `Notice` | A page-level message. `tone` plus a **symbol**, because colour alone is not an indicator anyone with a colour-vision deficiency can rely on. `role="alert"` for errors, `role="status"` for success |
| `Badge` | A small inline label. No interaction |
| `PageTitle` | §3 |

### Interaction states

Every interactive element has all five, and none is optional:

| State | Provided by |
|---|---|
| Rest | The variant |
| Hover | The variant's `hover:` classes |
| **Focus-visible** | The global ring in `globals.css`. Do not reimplement per component |
| Active / pressed | `whileTap` on `Button` and `Card`; disabled when the control cannot be pressed |
| Disabled | `disabled:opacity-60 disabled:cursor-not-allowed`, plus `aria-busy` when `pending` |

### Catalogue discovery — Illustrated Journal extension

ADR-037's approved catalogue extension reuses the editorial palette, type and
radii above. These rules are evidenced by `CourseCatalogue`, `CourseSearch` and
`CourseCard` source and desktop/mobile captures on 2026-10-14. The real local
catalogue has one published course; multi-course grid density and long content
remain covered by source rules and test fixtures, rather than populated browser
captures. Independent finish review is recorded in STATUS.md.

Search and browsing controls share a toolbar between horizontal rules, with
24px vertical padding. It stacks below `lg`; at `lg`, search and filters occupy
two columns with a 24px horizontal gap. Native labelled selects occupy two
columns on phones and a wrapping row from `sm`, with 12px gaps and a minimum
44px control height. The skill select appears only when course tags exist.

**Separate discovery modes.** Filters narrow the already-loaded catalogue;
ranked search replaces that listing and hides the filters. Empty or
one-character input keeps browsing available. Clear search returns focus to the
input and restores the current browse listing, preserving filter selections.
A refused search also restores that filtered listing while retaining the query
and inline error. The existing 400ms debounce, cancellation and API messages
remain the search contract.

Browse and ranked results use the same stretching grid: one column initially,
two from `sm` and three from `lg`, with 24px gaps. Each shared `CourseCard` is a
named article with 24px padding, 16px internal gaps, the inherited large radius
and a line border on the surface color. The title alone is a link; its heading
level follows the surrounding outline. The 24px display title has snug leading
and wraps, including unbroken strings. Language and expanded CEFR abbreviation
precede it. Optional descriptions use 14px muted text, relaxed leading and a
three-line clamp; optional instructor names and wrapping skill tags remain real
course metadata. Missing fields do not acquire invented content.

**Quiet course cards.** Shared course cards have no shadow or hover translation.
Hover strengthens the border; focus within accents it. Only border color
transitions (150ms); the title's keyboard focus uses the immediate global ring.
This domain treatment does not replace the elevated `Card` primitive above.

Publication-empty, filter-empty and search-empty copy remain distinct. Each
message sits between horizontal rules, with 48px vertical padding and a 36rem
maximum width. Recovery stays in the toolbar: Clear filters appears when filters
are active, and Clear search appears when the input contains text. Publication
emptiness explains review and publication rather than suggesting ineffective
filters. Result counts are announced politely.

---

## 6. Motion

### My Courses — quiet learner composition

The page uses a 56rem container with 24px horizontal padding, 40px vertical
padding initially and 64px from `sm`. Its existing `PageTitle` is followed by
a short introduction. The learner's system light/dark palette and sans display
face are preserved; this is not the public fixed-light shell.

The named course list renders immediately as native `ul`/`li` elements. Each
named article has 32px vertical padding and a bottom rule, without card elevation
or hover movement. Titles use 24px display text and wrap unbroken content.
Native progress bars are bounded by the available width and accompanied by
tabular lesson counts. Shared Start/Continue links have a minimum 44px height;
they fill mobile rows and align beside content from `sm`. Finished courses show
text plus a decorative check, rather than relying on success color alone.

Anonymous and empty states each use a named section between rules, with a 36px
Lucide book icon at 1.5px stroke, a 24px heading, explanatory copy and one action.
The empty state explains the existing enrollment behavior; the anonymous state
asks for sign-in. Error/retry and loading semantics retain the shared primitives.
No entrance animation, hover translation or progress animation is introduced.

### Shared ink stippling

`.ink-spots` is a static 128:76 CSS mask of explicitly positioned circles and
ellipses. It uses semantic ink at 85% opacity, has no pointer events, and is
always rendered with `aria-hidden="true"`, without focusable descendants.
It is hidden in forced-colors mode. It needs no bitmap, network asset, randomness
or image-generation service.

Public pages reserve a separate right-aligned band above the footer (96px wide,
128px from `sm`). Sign-in reserves space beneath its existing artwork. My Courses
places a 64px cluster beside the introduction, growing to 96px from `sm`.
Never put this motif behind reading content, controls or the active lesson player.

`MotionProvider` sits at the root and sets `reducedMotion="user"`. **Components
must not branch on `useReducedMotion()` during render.**

This is not a style preference. The hook reads a media query the server cannot;
branching on it made the server emit the animated branch with `opacity: 0` inline
while a reduced-motion client emitted the plain one, React declined to patch the
mismatch, and **the landing page rendered blank for exactly the people who had
asked for less motion.** A unit test asserted the branch and passed the whole
time, because it mocked the hook.

`motion.test.tsx` now asserts the property instead: rendered markup must not
depend on the preference. `Reveal` (scroll-triggered) and `StaggerList` (a list
that is a real `<ul>`, so a screen reader announces "list, 2 items") are the two
primitives; prefer them over hand-rolled variants.

Catalogue browse and ranked-search results render immediately, without
`StaggerList` or per-result entrance wrappers. Shared course-card border feedback
uses CSS as described in §5. Homepage featured-course and related-course list
wrappers retain their existing entrances; removing catalogue entrances does not
establish a global ban on list motion.

### Homepage illustration entrance

The homepage headline, description and navigation links are immediately present;
they have no stagger or motion wrapper. Only the decorative illustration enters
on mount: opacity 0 to 1 and vertical offset 8px to 0 over 280ms, with easing
`[0.16, 1, 0.3, 1]`. `MotionProvider` owns reduced-motion handling: transforms
are disabled while opacity can still animate. There is no render-time preference
branch. The four feature items have no entrance animation.

### Homepage composition — Illustrated Journal

ADR-037 scopes this composition to the public homepage. Its container is capped
at 80rem with 24px horizontal padding. Below `lg`, copy and links precede the
square artwork with a 16px grid gap; at `lg`, the hero uses a 0.9:1.1 two-column
grid with no gap. The primary action uses the shared button styles and an 18px
decorative arrow. Pricing is an underlined text link beneath it, with a minimum
44px target height. The supporting description is 18px serif with snug leading.

The generated listening-and-writing illustration is a 960 × 960 WebP
(`public/illustrations/learning-scene.webp`, 143,680 bytes). Its provenance and
prompt are in the adjacent `.webp.json`. Its ivory paper is part of the image
and sits on the public warm paper; orange belongs to the illustration pigment,
not a new UI token. The illustration is borderless, without rounded clipping or
blend mode; its original pigment colors are preserved.
The image has empty alternative text inside an `aria-hidden` wrapper because
the adjacent copy carries its meaning.

Four centered, unboxed items form a definition list between horizontal rules,
using 32px ink Lucide SVG icons with 1.5px strokes. They occupy one column
initially, two at `sm`, and four at `lg`, with vertical rules between columns;
descriptions use 14px muted text. The section heading remains accessible but
visually hidden. The real
published-course band follows. This is homepage composition, not a prohibition
on cards elsewhere.

### Sign-in composition — Illustrated Journal extension

ADR-037 extends this world to sign-in only. At `lg`, an 80rem container uses
equal columns: the form on the left and decorative artwork on the right. The
form is capped at 24rem, with a wordmark above and a catalogue link below.
Below `lg`, the complete form, recovery link and catalogue link precede the
artwork. The square art is capped at 256px initially and 320px at `sm`, then
fills its column at `lg`; it is borderless and has no rounded clipping.

The original notebook-opening illustration is a 960 × 960 WebP
(`public/illustrations/sign-in-scene.webp`), with generation prompt and source
recorded in the adjacent `.webp.json`. Intrinsic dimensions reserve its space.
It has empty alternative text inside an `aria-hidden` panel; the form carries
the page's meaning. Orange remains illustration pigment, not a UI token.

The sign-in form and art render immediately, with no entrance animation.
Shared fields, buttons, loading, error and focus feedback remain in use; login
behavior is unchanged. Registration and password recovery retain their existing
form entrance and desktop quotation-panel motion.

---

## 7. Theme

Learner and authentication screens other than sign-in follow
`prefers-color-scheme`, with no toggle or persistence (ADR-032). The root
declares `color-scheme: light dark` outside the editorial exception.

Public pages stay light under either OS preference (ADR-037), using scoped
tokens and `color-scheme: light` on the editorial shell and its document root.
The marketing layout selects `SiteShell variant="editorial"` statically;
styling needs no runtime API call or pathname lookup. Shared components inherit
semantic tokens from whichever surface contains them.

Sign-in also stays light under either OS preference, using the same editorial
tokens and document-root scheme (ADR-037's approved sign-in extension). The
existing client auth layout selects this local shell only when `usePathname`
is `/login` or `/login/`; registration and recovery retain the OS scheme.
This branch adds no request-time API call and does not change the marketing
layout's static shell selection.

The public header is in normal flow, with a plain bold 30px serif wordmark,
top navigation and no sidebar or mobile rail. The sign-in link has no visible
border. The footer keeps Courses, Pricing and Create account destinations;
the authenticated menu retains its existing account navigation. The learner
shell keeps its sticky header, mark and navigation rail.

---

## 7a. The mark, and the one file that cannot use a token

The learning variant of `SiteShell` draws the mark from utilities: a 36px square at
`rounded-(--radius-md)`, `bg-accent`, a semibold "L" in `text-on-accent`, and a
coral dot with a `border-surface` ring. Nothing special — it is inside the system
like everything else.

**`src/app/icon.svg` is the exception, and it is the interesting one.** A favicon is
a standalone file: it cannot read `globals.css`, so its colours are literals —
`#4945a5`, `#c44656`, `#ffffff`, `rx="12"`. Literals drift, and a favicon is the
last place anybody looks after a palette change.

So `seo.test.ts` parses the tokens out of `globals.css` and asserts the icon still
matches them. **Change the accent colour and that test fails** rather than leaving
the browser tab as the only thing still wearing the old brand. Light-mode values
throughout, deliberately: `prefers-color-scheme` inside an SVG favicon is honoured
inconsistently across browsers, and the accent square gives the glyph its own
background either way.

Until 2026-09-28 this file did not exist and the favicon was the **Next.js logo**,
straight from the `create-next-app` scaffold. ADR-035 §1.

**There is no `apple-icon` and no Open Graph image.** Both need raster assets, which
is a decision rather than an improvisation — ADR-035 §5.

---

## 8. Contributing

**Adding a variant to an existing primitive** — do it in the `cva` config, not at
the call site. A one-off class string at a call site is how the fifteen
hand-written `<h1>`s and five hand-written buttons happened.

**Adding a primitive** — only when two unrelated callers need it. One caller is a
component, not a primitive.

**Adding a dependency** — requires owner approval under CLAUDE.md §5, always.
`class-variance-authority`, `clsx`, `tailwind-merge`, `framer-motion` and
`lucide-react` are what exists; `cva` is described in `Button.tsx` as "the one
piece of the shadcn/ui toolchain this app actually needed", and Radix was
deliberately not added because nothing here is a dialog, menu or tab strip.

**Changing a token** — run the suite. `contrast.test.ts` will object if a value
drops below AA in either scheme, and that objection is correct.

**Before believing a new guard, provoke it.** ADR-006's rule, and this system has
repeatedly needed it: a reduced-motion test that passed while the bug shipped, a
conditional-wording assertion that matched a word in a different element, a
guard compiled into failure by its own docstring. **A guard that has never been
seen failing is not known to work.**

---

## 9. Where things are decided

| Question | Authority |
|---|---|
| Visual direction, palette, shell | ADR-029 |
| Public palette, shell and typography; homepage, sign-in and catalogue composition | ADR-037 |
| Accessibility target and verification | ADR-030, `docs/runbooks/accessibility-verification.md` |
| Error, loading and empty states | ADR-031, `docs/specs/frontend-state-and-api.md` |
| Theme behaviour | ADR-032; ADR-037 for fixed-light public routes and sign-in |
| Language, direction, captions metadata | ADR-033 |
| Static public routes | ADR-024 |
| Personalisation on static pages, refusal copy | ADR-026 |
| Anything about data, access or money | Not here. `CLAUDE.md` §4 and the backend ADRs |
