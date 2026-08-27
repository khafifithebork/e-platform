import Link from "next/link";

/**
 * The landing page, as a placeholder with honest content.
 *
 * **What was here until now was the create-next-app template** — a Vercel
 * logo, "to get started, edit the page.tsx file", and outbound links to
 * Vercel's templates gallery and the Next.js learn site. That was the
 * homepage of this product for fifteen milestones, and it used `zinc` and
 * `black` rather than any of the design tokens the rest of the app was built
 * on, which is a fair sign nobody had looked at it.
 *
 * This is deliberately not the finished landing page. **T7 is that**, and it
 * needs copy, a value proposition and probably a course carousel that T4's
 * listing makes possible. What this does is stop the shell wrapping somebody
 * else's marketing, and give the route group a reachable page so the layout is
 * exercised by the build.
 *
 * No data. Invariant 15, and this file is the easiest place in the group to
 * forget it: a landing page wanting to show "featured courses" is exactly the
 * change that adds a request-time fetch. When it does, the courses come from
 * `generateStaticParams`-adjacent build-time data (T9), not from a fetch here.
 */
export default function Home() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-24">
      <h1 className="font-display text-4xl leading-tight tracking-tight text-ink sm:text-5xl">
        Language courses, reviewed before they are published.
      </h1>

      <p className="max-w-xl text-lg leading-relaxed text-ink-muted">
        Video and audio lessons with transcripts and subtitles, from
        instructors whose courses passed a review. One subscription, every
        course.
      </p>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Link
          href="/courses"
          className="rounded-[--radius-md] bg-accent px-5 py-2.5 text-center
            font-medium text-white transition-colors hover:bg-accent-hover"
        >
          Browse the catalogue
        </Link>
        <Link
          href="/pricing"
          className="rounded-[--radius-md] border border-line-strong px-5 py-2.5
            text-center font-medium text-ink transition-colors hover:border-ink-subtle"
        >
          See pricing
        </Link>
      </div>
    </div>
  );
}
