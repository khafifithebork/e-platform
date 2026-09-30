import type { PublicCourseDetail } from "@/lib/catalogue/courses";

/**
 * What a share card says, and the colours it says it in.
 *
 * **Separate from the `opengraph-image.tsx` routes on purpose.** Those return a PNG
 * stream produced by WASM, which no unit test can meaningfully read — so every
 * decision that *can* be checked lives here, and the routes are left with layout
 * only. The build is what proves the images exist; these functions are what prove
 * they say the right thing.
 *
 * ## The colours are literals, like the favicon's
 *
 * `ImageResponse` renders outside the document: there is no stylesheet, no
 * `var(--color-accent)`, nothing to inherit. So the brand values are repeated here,
 * and repeated values drift — which is why `seo.test.ts` parses them out of
 * `globals.css` and asserts these match, the same guard `icon.svg` already has.
 *
 * ## The font will not match the site, and that is known
 *
 * This application ships no web fonts and uses a system stack deliberately
 * (`layout.tsx` explains why). Satori, which `ImageResponse` runs on, has no access
 * to system fonts — it only sees fonts handed to it or the one it bundles. A share
 * card therefore renders in something other than the site's own type.
 *
 * Accepted rather than solved: fixing it means committing a font file to serve one
 * 1200×630 image, and the alternative — the site adopting a web font so the two can
 * agree — is a much larger decision that `layout.tsx` explicitly declined.
 */

/** The accent square behind the mark, matching `--color-accent`. */
export const CARD_ACCENT = "#4945a5";
/** Text on the accent, matching `--color-on-accent`. */
export const CARD_ON_ACCENT = "#ffffff";
/** The card's own background, matching `--color-paper`. */
export const CARD_PAPER = "#f5f6fb";
/** Body text, matching `--color-ink`. */
export const CARD_INK = "#242442";
/** Secondary text, matching `--color-ink-muted`. */
export const CARD_INK_MUTED = "#53576f";
/** The dot on the mark, matching `--color-brand-coral`. */
export const CARD_CORAL = "#c44656";

/** Open Graph's expected card size. */
export const CARD_SIZE = { width: 1200, height: 630 } as const;

/**
 * Where a title stops.
 *
 * A share card has one line of large type and no scrollbar, so a long title has to
 * be cut somewhere — and cutting it in the renderer means discovering the limit from
 * a screenshot. 70 characters is roughly two lines at this size; the longest course
 * title the catalogue allows is 200, which would overflow the card entirely.
 */
export const MAX_TITLE = 70;

/** A title that fits, with an ellipsis when it did not. */
export function fit(title: string, limit = MAX_TITLE): string {
  const trimmed = title.trim();
  if (trimmed.length <= limit) return trimmed;

  // Cut at a word boundary where there is one nearby, so the card does not end
  // mid-word. `…` rather than "..." — one character, and screen readers handle it.
  const cut = trimmed.slice(0, limit);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > limit - 15 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
}

/**
 * CEFR levels spelled out, for the card's subtitle.
 *
 * The same table `CourseCard` carries, and deliberately a second copy rather than a
 * shared import: that one is a React component in the client bundle, and this runs at
 * build time inside an image renderer. A missing key falls back to the code, so a
 * level added server-side degrades to what it already was.
 */
const LEVEL_NAMES: Record<string, string> = {
  A1: "Beginner",
  A2: "Elementary",
  B1: "Intermediate",
  B2: "Upper intermediate",
  C1: "Advanced",
  C2: "Proficient",
};

/**
 * What a course's card says.
 *
 * **Not the description.** A course description is up to a paragraph and often empty
 * — `t8-spanish` has none today — so a card built on it is either overflowing or
 * blank. The language and level are always present, they are what somebody deciding
 * whether to open a shared link wants, and they cannot be missing.
 */
export function courseCardText(course: PublicCourseDetail): {
  title: string;
  subtitle: string;
} {
  const level = LEVEL_NAMES[course.level]
    ? `${course.level} · ${LEVEL_NAMES[course.level]}`
    : course.level;

  return {
    title: fit(course.title),
    subtitle: `${course.language.name} · ${level}`,
  };
}
