import Link from "next/link";

import { FeaturedCourses } from "@/components/catalogue/FeaturedCourses";
import { allPublishedCourses } from "@/lib/catalogue/courses";

/**
 * The landing page.
 *
 * **Every claim here is one the code can keep.** That is the whole editorial
 * constraint, and it removed most of what a landing page usually says:
 *
 * - **No price, and no "from £x".** CLAUDE.md §11 #1 — the payment provider
 *   and operating jurisdiction are unresolved, Stripe is unavailable to
 *   Moroccan merchants, and a merchant of record may be required. §6 forbids
 *   inventing a price. `/pricing` explains the same absence at length.
 * - **No "start your free trial".** A trial exists in the data model and can
 *   only be started by `manage.py billing start --trial-days`. There is no
 *   self-serve path to one, so the button would be a promise the product
 *   cannot keep today. It arrives with M8.
 * - **No learner counts, no testimonials, no ratings.** None of those exist as
 *   data, and inventing them is the same failure as inventing a price with a
 *   nicer name.
 *
 * What is left is true: courses are reviewed before publication (the review
 * workflow is real), lessons carry transcripts and subtitles (M6), progress
 * resumes across devices (M7), and lessons are video, audio or text.
 *
 * **Data is read at build time**, like the rest of this route group — invariant
 * 15. The featured band is a slice of the same catalogue `/courses` renders,
 * not a second endpoint.
 */
export default async function Home() {
  const courses = await allPublishedCourses();

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-20 px-6 py-20">
      <section className="flex max-w-2xl flex-col gap-6">
        <h1 className="font-display text-4xl leading-tight tracking-tight text-ink sm:text-5xl">
          Language courses, reviewed before they are published.
        </h1>

        <p className="text-lg leading-relaxed text-ink-muted">
          Every course here was submitted by an instructor and approved by a
          person before anyone could see it. No open marketplace, no
          auto-published backlog.
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
      </section>

      <FeaturedCourses courses={courses} />

      <section aria-labelledby="what-you-get" className="flex flex-col gap-6">
        <h2 id="what-you-get" className="font-display text-2xl text-ink">
          What is in every course
        </h2>

        {/*
         * A description list, not a grid of divs. Each item is a term and its
         * explanation, which is what `<dl>` is for — and it gives assistive
         * technology the pairing without any ARIA.
         */}
        <dl className="grid gap-8 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <dt className="font-medium text-ink">Video, audio and written lessons</dt>
            <dd className="text-ink-muted">
              A lesson is whichever of those suits it. Listening practice does
              not need a video of somebody talking.
            </dd>
          </div>

          <div className="flex flex-col gap-2">
            <dt className="font-medium text-ink">Transcripts and subtitles</dt>
            <dd className="text-ink-muted">
              Every spoken lesson is transcribed, so you can read along, search
              inside it, or follow without sound.
            </dd>
          </div>

          <div className="flex flex-col gap-2">
            <dt className="font-medium text-ink">Progress that follows you</dt>
            <dd className="text-ink-muted">
              Where you stopped is remembered per lesson, and picking up on
              another device continues from the same place.
            </dd>
          </div>

          <div className="flex flex-col gap-2">
            <dt className="font-medium text-ink">Reviewed, not just uploaded</dt>
            <dd className="text-ink-muted">
              An administrator reads a course before it is published, and can
              send it back. That is the whole reason this catalogue is small.
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
