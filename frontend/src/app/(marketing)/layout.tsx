import Link from "next/link";

import { AuthMenu } from "@/components/auth/AuthMenu";

/**
 * The public shell — everything a visitor sees before signing in.
 *
 * architecture.md:937 put "landing, pricing, public course pages" in a
 * `(marketing)` route group at M0 and nothing was ever built in it. This is
 * that group, and CLAUDE.md invariant 15 is what shapes it: **nothing under
 * here may fetch at request time.** Every page in this group is statically
 * generated, so this layout holds navigation and chrome and no data.
 *
 * That is not a performance preference. A request-time fetch here would cross
 * the public internet under B-lite — Next on Cloudflare Workers, Django on
 * Hetzner, no private network between them — and would need its own
 * authentication. Keeping this layout data-free is what keeps CLAUDE.md §11 #5
 * moot.
 *
 * **A nested layout, not a second root layout.** `app/layout.tsx` already
 * declares `<html>` and `<body>`. Next's route-group documentation is explicit
 * that navigating between *multiple root layouts* forces a full page reload;
 * nesting under the existing root avoids that, so moving between a marketing
 * page and the auth pages stays a client-side transition.
 *
 * **No `"use client"`.** This renders on the server and ships no JavaScript.
 * Abuse case 7: a public page that needs hydration to show its content is not
 * statically generated in any sense a visitor benefits from.
 */

/** Where the header points. Kept as data so the nav test can assert the set. */
const NAV = [
  { href: "/courses", label: "Courses" },
  { href: "/pricing", label: "Pricing" },
] as const;

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      {/*
       * The skip link, first in the DOM and visible only on focus.
       *
       * Every page in this group starts with the same header, so a keyboard or
       * screen-reader user would otherwise tab through the whole navigation on
       * each one before reaching anything new. `sr-only focus:not-sr-only` is
       * what makes it invisible to a mouse user and present for everyone else.
       */}
      <a
        href="#main"
        className="sr-only rounded-[--radius-sm] bg-accent px-4 py-2 text-sm
          font-medium text-on-accent focus:not-sr-only focus:absolute focus:left-4
          focus:top-4 focus:z-50"
      >
        Skip to content
      </a>

      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-6 px-6 py-5">
          <Link
            href="/"
            className="font-display text-xl tracking-tight text-ink hover:text-accent"
          >
            Lingua
          </Link>

          {/*
           * Labelled, because a page may grow a second nav — a footer one
           * already exists below — and "navigation" twice in the landmark list
           * tells a screen-reader user nothing about which is which.
           */}
          <nav aria-label="Main" className="flex items-center gap-6 text-sm">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="text-ink-muted hover:text-ink">
                {item.label}
              </Link>
            ))}
            {/*
             * The one personalised thing in an otherwise static shell.
             *
             * A client component, so the prerendered HTML stays identical for
             * everyone and invariant 15 holds. It resolves who you are in the
             * browser and renders "Sign in" or your account — starting from
             * neither, because rendering the signed-out state as a placeholder
             * flashes "Sign in" at somebody who is signed in.
             */}
            <AuthMenu />
          </nav>
        </div>
      </header>

      {/*
       * `tabIndex={-1}` so the skip link can move focus here. Without it the
       * browser scrolls to the anchor and leaves focus on the link, so the
       * next Tab goes back into the navigation the user just skipped.
       */}
      <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">
        {children}
      </main>

      <footer className="border-t border-line">
        <div
          className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-8 text-sm
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
