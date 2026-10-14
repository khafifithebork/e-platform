# ADR-037: Illustrated Journal homepage

## Catalogue extension — approved 2026-10-14

The owner approved grouping catalogue search and filters in a compact responsive
toolbar, widening desktop results from four columns to three, quieting shared
course cards and improving empty-state recovery. The existing C semantic tokens
and real course metadata remain the visual and content authority. No new artwork,
dependency or API shape is introduced. Course cards retain named article semantics
and title-only links; long titles wrap and optional content stays optional.

Catalogue browse and ranked search results render immediately, without staggered
entrances. Shared course cards no longer translate or animate shadows on hover;
border color feedback uses 150ms CSS transitions, while keyboard focus stays
immediate and visible. The existing hydration-safe MotionProvider is unchanged.
No new motion is added. Homepage/related-course list wrappers retain their existing
behavior; this batch removes repeated entrances from catalogue results only.

Search debounce, cancellation, ranking and API messages remain unchanged. A clear
search action restores input focus and browsing. A refused search now restores
the already-loaded, currently filtered catalogue while keeping its query and error
available: a regression test exposed that the previous parent hid content despite
the search child's documented fallback. Search and filters remain alternative
discovery modes. One-character input leaves browsing available. Publication-empty,
filter-empty and search-empty messages remain distinct. Public routes still read
catalogue data at build time (invariant 15); generated API types are unchanged.

Retested 2026-10-14 after restoring local Docker/API startup: all 688 frontend
tests, production build/TypeScript, lint and four production-artifact gates pass.
API health and the local production-settings Django deployment check pass.
Desktop/mobile, actual search-empty recovery, keyboard focus, filters and course
navigation were checked. The independent reviewer returned `ship` for the approved
catalogue scope, with no material fixes. Only one real course is published locally;
multiple-card density and long-content reflow have source/test evidence only.
Browser dark-theme and reduced-motion emulation remain unavailable.

## Sign-in extension — approved 2026-10-13

The owner approved extending C to sign-in only, with an original companion
illustration. `/login/` reuses the existing editorial semantic tokens and serif
display face, with the form on the left and artwork on the right on desktop.
On mobile the complete form and catalogue link precede the compact artwork.
Registration and password recovery retain their existing theme and layout.
This supersedes the authentication-theme exclusion below only for sign-in.

The existing client auth layout uses `usePathname` to select this local variant;
the marketing shell remains statically selected. Only `/api/*` is rewritten, so
the auth pathname has the same server and browser value. No request-time API call
is added. Invariants 9, 15 and 16 and all login behavior are preserved.

The sign-in form and illustration render visibly without an entrance animation.
Shared field, button, loading, error and focus feedback remain in use. There is
no new motion and no reduced-motion preference read during hydration.

Original artwork was generated with built-in image_gen using the homepage
illustration as a style reference: a learner opening a notebook, patterned
clothing, ink outlines, stippled texture and restrained indigo/orange pigment.
Delivery: `frontend/public/illustrations/sign-in-scene.webp` (960px square).
Its adjacent JSON records the exact generation prompt and source. It is
decorative (`alt=""`, `aria-hidden` panel), with reserved intrinsic dimensions.
No Figma file was provided and no Figma asset is claimed.

Status: accepted 2026-10-08; public palette and shell expansion approved 2026-10-12.

## Direction contract

**THESIS:** Learning as a thoughtful personal practice: a real illustration of

listening and writing replaces the anonymous stack of empty cards.

**OWN-WORLD:** Indigo actions retain their meaning. Ink outlines, stippled print,

striped clothing and small warm orange areas live inside a paper illustration.

Public pages now use warm ivory paper, near-black ink, serif headings and deep

indigo actions. Operating screens retain their existing typography and theme tokens.

**STORY:** Understand that courses are reviewed, see the available learning tools,

then browse the actual catalogue. No fabricated social proof or trial promise.

**FIRST VIEWPORT:** A large serif headline and two immediately usable links sit

beside a square illustration on desktop. Mobile puts the links before the art.

Four centered benefits separated by thin rules follow, then the existing

published-course band. A plain serif wordmark and top navigation replace the public sidebar.

**FORM:** C, Illustrated Journal, selected from the three-direction comparison

by the owner. Code-led adaptation of that decision comp, not a pixel-identical

Figma specification. The October 12 approval removes the public sidebar while

preserving navigation destinations; learner navigation remains unchanged.

The concept roll was skipped because the owner explicitly selected C; there is

no seed key to report. Product requirements remain in CLAUDE.md §3 and

docs/architecture.md; no duplicate PRODUCT.md is introduced in this scoped batch.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the

finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

For this extension, the incumbent `docs/design-system.md` is the system record;

do not introduce a competing global design system. Public token overrides are

scoped to SiteShell editorial; global learner/auth tokens are unchanged.

## Implementation constraints

Use the platform serif stack for public headings; no new font dependency or

unlicensed font file. Existing title variants remain unchanged. Keep all public

data reads at build time (invariant 15). No business behavior changes.

Art has fixed intrinsic dimensions and empty alternative text because the

surrounding copy carries the meaning. Its border and rounded container are removed;

its original paper sits directly on the warm page without multiply darkening. Orange remains illustration

pigment, never UI text. Existing artwork is reused, not copied from another platform.

## Public palette and shell revision — 2026-10-12

The owner rejected retaining the dark application shell around C and approved the

warm public treatment. This supersedes ADR-032's system theme behavior only for

public routes: public paper remains light in either OS preference. Learner and

authentication routes keep their current light/dark palettes.

Scoped tokens: paper/surface #faf7f0; ink #191919; muted #50505a; subtle #5b5963;

accent #4541b5, hover #343087, on-accent #ffffff; line #d1ccc3, strong #817b72.

Public radii are 3/4/8px. Shared controls consume the inherited semantic tokens.

The public shell is still a Server Component, explicitly selected by the marketing

layout. No request headers, pathname hook or runtime API call choose its style.

Account creation remains linked from the public footer; AuthMenu retains account,

My Courses and sign-out destinations when signed in. Hero pricing is an underlined

link, and the primary action gains a decorative arrow from existing Lucide icons.

No new animation or dependency is added.

## Motion

Only the decorative illustration introduces itself, once per homepage mount:

280ms, opacity 0 to 1 and y 8px to 0, ease [0.16, 1, 0.3, 1]. This introduces

the learning scene without postponing the headline or actions. The existing

hydration-safe MotionProvider removes transforms for reduced motion and retains

the fade. Remove hero parallax, text staggering, extra focusable press wrappers

and feature entrances. Existing shared button color feedback remains 150ms.

## Asset provenance

Original illustration generated using the built-in image generator, from the

owner-approved C comparison board. No competitor artwork was copied. No Figma

file was supplied; connector access is verified but no Figma assets are used.

Generation source: `exec-673f65e9-74f1-41b5-aca0-d0f259557bed.png`.

Delivery: `frontend/public/illustrations/learning-scene.webp`.

## Verification

Implemented; confirmation build and 14 focused tests passed on 2026-10-12.

The full frontend suite passed all 655 tests with two workers. An earlier run

concurrent with the build had 11 auth-test failures, predominantly timeouts;

no assertions or timeouts were changed. TypeScript, lint, static-route,

page-structure, CSS-token and bundle checks passed. The final homepage remains

static, with real local catalogue data supplied by Django at build time.

Dark-theme desktop/mobile captures and keyboard catalogue navigation were

verified. The first visual review requested balanced mobile title wrapping and

updated documentation; one correction batch addresses those findings. Browser

light-theme and reduced-motion emulation remain unavailable and unverified.

Both-palette contrast tests pass; the existing MotionProvider is unchanged.

Final reviewer disposition: `fix`. Roll provenance, mobile typography and system

documentation were scored resolved. Its separate PRODUCT.md convention remains

unmet; the existing authoritative product documents are retained under this

batch's scope. No visual fixes remain among the scored findings. This is a

verdict on that fix list, not certification of the untested browser matrix.

Public-palette revision verification: 674 full frontend tests passed; 88 targeted
palette/shell tests passed after corrections. Final build, TypeScript, lint and
all four production-artifact gates passed. Six desktop/mobile captures confirmed
the public theme; keyboard focus, pricing navigation, search empty state and
restoration of the auth theme were verified. The reviewer returned `ship` for the
four scored fixes (paper ground, image blending, sign-in border, documentation).
This supersedes the earlier homepage review for this approved expanded scope;
it does not certify browser reduced-motion emulation, which remains unavailable.
