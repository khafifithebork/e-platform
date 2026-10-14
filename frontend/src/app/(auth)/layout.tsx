"use client";

import { motion } from "framer-motion";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The auth shell.
 *
 * Sign-in uses the approved Illustrated Journal treatment. Other auth steps
 * keep two columns on wide screens: the form on the left where the eye starts, and
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
  const pathname = usePathname();

  // This layout persists across auth navigation. Select the approved sign-in
  // treatment here so registration and recovery keep their existing shell.
  if (pathname === "/login" || pathname === "/login/") {
    return (
      <div data-site-style="editorial" className="min-h-dvh bg-paper text-ink">
        <div className="mx-auto grid min-h-dvh max-w-7xl lg:grid-cols-2">
          <main className="flex flex-col px-6 py-8 sm:px-12 lg:px-16 lg:py-10">
            <Link href="/" className="w-fit font-display text-3xl font-bold tracking-tight text-ink hover:text-accent">
              Lingua
            </Link>
            <div className="flex flex-1 items-center py-12 lg:py-16">
              <div className="mx-auto w-full max-w-sm">{children}</div>
            </div>
            <footer className="text-sm text-ink-subtle">
              <Link href="/" className="underline decoration-line-strong underline-offset-4 hover:text-ink">
                Back to the catalogue
              </Link>
            </footer>
          </main>
          <aside aria-hidden="true" className="flex items-center justify-center px-6 pb-8 sm:px-12 lg:px-4 lg:py-12">
            <Image
              src="/illustrations/sign-in-scene.webp"
              alt=""
              width={960}
              height={960}
              unoptimized
              loading="eager"
              className="h-auto w-full max-w-64 sm:max-w-xs lg:max-w-none"
            />
          </aside>
        </div>
      </div>
    );
  }

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
            initial={{ opacity: 0, y: 12 }}
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
          initial={{ opacity: 0, x: 16 }}
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
