"use client";

import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";

/**
 * The auth shell.
 *
 * Two columns on wide screens: the form on the left where the eye starts, and
 * a quiet editorial panel on the right. The panel is decorative and is hidden
 * from assistive technology and from small screens entirely — a signed-out
 * user on a phone wants the form, not a mission statement.
 *
 * **A client component, unlike the marketing layout.** Invariant 15's
 * static-rendering requirement is scoped to `(marketing)`; nothing about the
 * auth flow needs to be prerendered, and every page under it already has its
 * own `"use client"` for form state. Making the layout itself a client
 * component here is simpler than the split `SiteShell`/`Hero` use to keep
 * `(marketing)` server-only — there is no equivalent constraint to protect.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const reduceMotion = useReducedMotion();

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <main className="flex flex-col px-6 py-10 sm:px-12 lg:px-16">
        <Link
          href="/"
          className="font-display text-xl tracking-tight text-ink hover:text-accent"
        >
          Lingua
        </Link>

        <div className="flex flex-1 items-center py-12">
          <motion.div
            initial={reduceMotion ? undefined : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-sm"
          >
            {children}
          </motion.div>
        </div>

        <footer className="text-sm text-ink-subtle">
          <Link href="/" className="hover:text-ink">
            Back to the catalogue
          </Link>
        </footer>
      </main>

      <aside
        aria-hidden="true"
        className="relative hidden flex-col justify-center overflow-hidden
          bg-surface-sunken px-16 lg:flex"
      >
        {/* The same glow the landing page uses behind its hero, at rest here
            rather than centred on any one line of the quote — it is texture
            for the panel, not emphasis for the text. */}
        <div
          className="pointer-events-none absolute inset-0
            bg-[radial-gradient(ellipse_50%_40%_at_80%_20%,var(--color-accent-subtle),transparent)]"
        />

        <motion.blockquote
          initial={reduceMotion ? undefined : { opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="relative max-w-md"
        >
          <p className="font-display text-3xl leading-snug text-ink">
            A language is not a subject to be finished. It is a habit, built
            fifteen minutes at a time.
          </p>
          <footer className="mt-6 text-sm text-ink-muted">
            Every course here is reviewed before it is published.
          </footer>
        </motion.blockquote>
      </aside>
    </div>
  );
}
