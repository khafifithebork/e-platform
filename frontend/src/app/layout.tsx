import type { Metadata } from "next";

import { MotionProvider } from "@/components/motion/MotionProvider";
import { siteUrl } from "@/lib/site";

import "./globals.css";

/*
 * No `next/font/google`.
 *
 * create-next-app wires up Geist from Google Fonts, which means every build
 * needs to reach fonts.googleapis.com. On a machine that cannot — this one —
 * the build emits a warning and silently substitutes a fallback, so the font
 * you tested is not the font you shipped. A system stack is honest about what
 * it renders, costs no request, and cannot shift layout on load.
 *
 * If a licensed brand face is chosen later, self-host it with
 * `next/font/local` rather than reintroducing the network dependency.
 */
/** One description, so the page copy and the link preview cannot drift apart. */
const DESCRIPTION =
  "Curated language courses, reviewed before publication. Video and audio lessons with transcripts.";

/**
 * Root metadata.
 *
 * **`metadataBase` is the whole reason `siteUrl()` exists.** Next resolves every
 * relative `alternates.canonical` and every Open Graph URL against it, and with no
 * base it emits either nothing or a warning-laden localhost URL. Left `undefined`
 * when no origin is configured, which is what makes the missing-origin case emit
 * no canonical rather than a wrong one — see `src/lib/site.ts`.
 *
 * **`openGraph.images` is not set here, and does not need to be.** Next detects
 * `opengraph-image.tsx` beside a route and emits the `og:image` tags itself, with the
 * absolute URL, the dimensions and the alt text — so writing them by hand would be a
 * second source for the same fact. `src/app/opengraph-image.tsx` is the site card and
 * `(marketing)/courses/[slug]/opengraph-image.tsx` is the per-course one, both
 * generated at build time (2026-09-30, ADR-035 §5).
 *
 * **No `alternates.canonical` here, and that is the subtle one.** Metadata is
 * inherited, so a canonical on the root layout becomes every route's canonical
 * unless that route overrides it — which would have `/login` telling crawlers its
 * real address is `/`, the strongest possible instruction to treat two different
 * pages as one. Canonicals belong to the pages that have them, and only the public
 * ones do: `publicMetadata()` in `src/lib/site.ts` builds them, and `seo.test.ts`
 * asserts no other route group grows one.
 *
 * `openGraph.url` is left out for the same reason.
 */
export const metadata: Metadata = {
  metadataBase: siteUrl() ?? undefined,
  title: {
    default: "Lingua",
    template: "%s · Lingua",
  },
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "Lingua",
    locale: "en",
  },
  twitter: {
    /*
     * `summary_large_image` since 2026-09-30, and the comment it replaces is worth
     * keeping in view: this was `summary` because "the large card is defined by its
     * image, and there is no image yet. Claiming the layout without the asset renders
     * an empty box."
     *
     * The asset now exists — `opengraph-image.tsx`, which Twitter falls back to when
     * there is no `twitter-image` — so the large card has something to show. If the
     * images are ever removed, this goes back.
     */
    card: "summary_large_image",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  /*
  * `scroll-pb-20` is WCAG 2.2 AA, 2.4.11 Focus Not Obscured (Minimum).
  *
  * Below `xl`, `SiteNavTree` renders a fixed "Site map" button at the bottom
  * left. Tabbing to an element just below the fold makes the browser scroll it
  * in *minimally* — `block: "nearest"` — parking it flush against the bottom
  * edge, exactly where that button sits, so the focus ring ends up behind it.
  * Reproduced at 420×480 on `/courses` before being fixed (ADR-006): the course
  * card's link and both footer links all landed under it.
  *
  * 5rem of scroll padding keeps scroll-into-view clear of the button, which
  * occupies the bottom 62px. `xl:scroll-pb-0` because above that breakpoint the
  * navigation is a static rail and there is nothing fixed to hide behind.
  *
  * **Tailwind utilities rather than a rule in `globals.css`**, and that is not a
  * style preference. The first attempt wrote
  * `@media (width < 80rem) { :root { scroll-padding-bottom: 5rem } }` by hand,
  * and **the entire block was silently dropped from the compiled stylesheet** —
  * the rules either side of it survived, so nothing looked wrong. The range
  * syntax is what did it. Utilities go through Tailwind's own breakpoints and
  * cannot vanish that way. This is the second time in this codebase that CSS has
  * disappeared without an error — the first was the `[--token]` syntax, 45 classes
  * that never applied in any release — which is why a test now asserts this one
  * reaches the compiled output rather than trusting that it did.
  */
  return (
    <html lang="en" className="h-full scroll-pb-20 xl:scroll-pb-0">
      {/*
       * `MotionProvider` is a client component, and wrapping the tree in one
       * does not make any page dynamic — the `(marketing)` group still
       * prerenders (invariant 15, asserted by `verify:static`). It sits at the
       * root because reduced motion is a property of the visitor, not of a
       * route, and because the bug it fixes was every component answering that
       * question separately during render.
       */}
      <body className="min-h-full">
        <MotionProvider>{children}</MotionProvider>
      </body>
    </html>
  );
}
