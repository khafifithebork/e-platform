import Link from "next/link";

/**
 * The auth shell.
 *
 * Two columns on wide screens: the form on the left where the eye starts, and
 * a quiet editorial panel on the right. The panel is decorative and is hidden
 * from assistive technology and from small screens entirely — a signed-out
 * user on a phone wants the form, not a mission statement.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
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
          <div className="w-full max-w-sm">{children}</div>
        </div>

        <footer className="text-sm text-ink-subtle">
          <Link href="/" className="hover:text-ink">
            Back to the catalogue
          </Link>
        </footer>
      </main>

      <aside
        aria-hidden="true"
        className="hidden flex-col justify-center bg-surface-sunken px-16 lg:flex"
      >
        <blockquote className="max-w-md">
          <p className="font-display text-3xl leading-snug text-ink">
            A language is not a subject to be finished. It is a habit, built
            fifteen minutes at a time.
          </p>
          <footer className="mt-6 text-sm text-ink-muted">
            Every course here is reviewed before it is published.
          </footer>
        </blockquote>
      </aside>
    </div>
  );
}
