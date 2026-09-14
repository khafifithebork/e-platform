import Link from "next/link";

import { AuthMenu } from "@/components/auth/AuthMenu";
import { NavLinks } from "@/components/site/NavLinks";
import { SiteNavTree } from "@/components/site/SiteNavTree";

/**
 * The chrome every page outside the auth flow wears.
 *
 * **Extracted at M16 T9, because the learner pages had none.** `(marketing)`
 * carried this markup inline, and `(learner)` — added at T3 for the lesson
 * route and at T5 for "my courses" — had no layout at all. So a learner who
 * followed "My courses" out of the header arrived somewhere with no header,
 * no footer, no navigation and no skip link, and browser-back was the only way
 * out. Found by reading the built HTML rather than the source: the whole page
 * was "My courses · Lingua / My courses / Loading your courses…".
 *
 * One component rather than two layouts that look alike, because two would
 * drift — and the half that drifts is the one nobody has open when they change
 * the other.
 *
 * A Server Component. `AuthMenu` inside it is the only client boundary, which
 * is what keeps the `(marketing)` pages statically generated (invariant 15)
 * while still greeting somebody by name.
 */

/** Where the header points. Kept as data so a test can assert the set. */
const NAV = [
  { href: "/courses", label: "Courses" },
  { href: "/pricing", label: "Pricing" },
] as const;

export function SiteShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      {/*
       * The skip link, first in the DOM and visible only on focus.
       *
       * Every page wearing this shell starts with the same header, so a
       * keyboard or screen-reader user would otherwise tab through the whole
       * navigation on each one before reaching anything new.
       */}
      <a
        href="#main"
        className="sr-only rounded-[--radius-sm] bg-accent px-4 py-2 text-sm
          font-medium text-on-accent focus:not-sr-only focus:absolute focus:left-4
          focus:top-4 focus:z-50"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-line bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-5">
          <Link
            href="/"
            className="flex items-center gap-2 font-display text-xl tracking-tight
              text-ink transition-colors hover:text-accent"
          >
            {/*
             * A mark, not a logo file — one glyph in the accent colour, so the
             * wordmark reads as a product rather than plain text in the header.
             * Decorative: the name beside it already says "Lingua" to a screen
             * reader.
             */}
            <span
              aria-hidden="true"
              className="flex h-6 w-6 items-center justify-center rounded-[--radius-sm]
                bg-accent text-sm font-semibold text-on-accent"
            >
              L
            </span>
            Lingua
          </Link>

          {/*
           * Labelled, because a page may grow a second nav — the footer one
           * below already is — and "navigation" twice in the landmark list
           * tells a screen-reader user nothing about which is which.
           */}
          <nav aria-label="Main" className="flex items-center gap-6 text-sm">
            <NavLinks items={NAV} />

            {/*
             * The one personalised thing in an otherwise impersonal shell. A
             * client component, so the prerendered HTML stays identical for
             * everyone and invariant 15 holds.
             */}
            <AuthMenu />
          </nav>
        </div>
      </header>

      {/*
       * `tabIndex={-1}` so the skip link can move focus here. Without it the
       * browser scrolls to the anchor and leaves focus on the link, so the
       * next Tab goes straight back into the navigation the user just skipped.
       */}
      <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">
        {/*
         * The sidebar and the page content share this row so `SiteNavTree`'s
         * column sits in the margin a fixed content width otherwise leaves
         * empty, without each page's own `max-w-7xl` container having to know
         * a sidebar exists. No `items-start`: the default `stretch` is what
         * lets the sidebar's background and right border run the full height
         * of whatever page sits beside it, rather than stopping after its own
         * short list of links. Below `xl`, `SiteNavTree` renders nothing here
         * at all — its mobile form is a fixed-position toggle — so
         * `min-w-0 flex-1` is simply the whole width down there.
         */}
        <div className="flex w-full">
          <SiteNavTree />
          <div className="min-w-0 flex-1">{children}</div>
        </div>
      </main>

      <footer className="border-t border-line">
        <div
          className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-8 text-sm
            text-ink-subtle sm:flex-row sm:items-center sm:justify-between"
        >
          <p>Every course here is reviewed before it is published.</p>

          <nav aria-label="Footer" className="flex gap-6">
            <Link href="/courses" className="hover:text-ink">
              Courses
            </Link>
            <Link href="/pricing" className="hover:text-ink">
              Pricing
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
