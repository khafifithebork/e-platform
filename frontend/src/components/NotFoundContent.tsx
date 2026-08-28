import Link from "next/link";

/**
 * What a 404 says, in one place.
 *
 * Rendered by two boundaries that Next treats very differently, which is the
 * reason this is a shared component rather than one file:
 *
 * - `app/not-found.tsx` — the site-wide 404. **This is the one that actually
 *   serves refused course slugs.** `courses/[slug]` sets
 *   `dynamicParams = false`, and a slug `generateStaticParams` did not return
 *   is refused by the router *before* the segment renders, so the segment's
 *   own `not-found.tsx` never runs.
 * - `app/(marketing)/not-found.tsx` — reached when `notFound()` is called
 *   while rendering a page in that group, which happens when the API answers
 *   404 for a course during the build.
 *
 * **That first point is a correction.** This component was written believing
 * the group's boundary handled refused slugs; serving the build and requesting
 * an unknown one returned Next's default unstyled 404 instead. Verified
 * against a running `next start`, not inferred from the docs.
 *
 * The copy leads with "the link may be old" rather than "you mistyped
 * something", because the common way to arrive here is following a saved link
 * to a course that was unpublished since the last build.
 */
export function NotFoundContent() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-24">
      <h1 className="font-display text-3xl tracking-tight text-ink">
        That page is not here
      </h1>

      <p className="max-w-prose leading-relaxed text-ink-muted">
        The link may be old, or the course may have been taken down. Courses are
        reviewed before publication and can be withdrawn afterwards, so a link
        that worked last month is not guaranteed to work now.
      </p>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Link
          href="/courses"
          className="rounded-[--radius-md] bg-accent px-5 py-2.5 text-center
            font-medium text-on-accent transition-colors hover:bg-accent-hover"
        >
          Browse the catalogue
        </Link>
        <Link
          href="/"
          className="rounded-[--radius-md] border border-line-strong px-5 py-2.5
            text-center font-medium text-ink transition-colors hover:border-ink-subtle"
        >
          Go to the home page
        </Link>
      </div>
    </div>
  );
}
