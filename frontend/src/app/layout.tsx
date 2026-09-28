import type { Metadata } from "next";

import { MotionProvider } from "@/components/motion/MotionProvider";

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
export const metadata: Metadata = {
  title: {
    default: "Lingua",
    template: "%s · Lingua",
  },
  description:
    "Curated language courses, reviewed before publication. Video and audio lessons with transcripts.",
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
