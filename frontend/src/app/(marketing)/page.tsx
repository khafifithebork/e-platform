import { BookOpen, Captions, RotateCcw, BadgeCheck } from "lucide-react";
import type { Metadata } from "next";

import { FeaturedCourses } from "@/components/catalogue/FeaturedCourses";
import { Hero } from "@/components/site/Hero";
import { allPublishedCourses } from "@/lib/catalogue/courses";
import { publicMetadata } from "@/lib/site";

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
 *
 * **`Hero` is the only client-boundary crossing on this page**, same
 * reasoning as `AuthMenu` and `CourseProgress`: it needs mount-triggered
 * motion, which is a browser concern, so only that
 * section crosses the boundary. `Home` itself stays `async` and server-only,
 * so the page is still built once and served identically to everyone.
 */
/**
 * The landing page's own metadata, for its canonical URL and share card.
 *
 * `absoluteTitle`, because the root template would compose this one into
 * "Lingua · Lingua". The description is the site description rather than a second
 * version of it — this page is what the site is.
 */
export const metadata: Metadata = publicMetadata({
  title: "Lingua",
  description:
    "Curated language courses, reviewed before publication. Video and audio lessons with transcripts.",
  path: "/",
  absoluteTitle: true,
});

export default async function Home() {
  const courses = await allPublishedCourses();

  return (
    <div className="flex flex-col gap-0">
      <Hero />

      <div className="mx-auto flex w-full max-w-7xl flex-col gap-14 sm:gap-20 px-6 pb-20">
        <section aria-labelledby="what-you-get" className="flex flex-col gap-6 border-y border-line py-8 sm:py-10">
          <div className="sr-only"><h2 id="what-you-get" className="font-display text-2xl text-ink">
            What is in every course
          </h2></div>

          <dl className="grid gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex min-w-0 flex-col gap-2 px-5 text-center sm:even:border-s sm:even:border-line lg:[&+div]:border-s lg:[&+div]:border-line">
              <dt className="flex flex-col items-center gap-4 font-medium text-ink">
                <BookOpen aria-hidden="true" size={32} strokeWidth={1.5} className="text-ink" />
                Video, audio and written lessons
              </dt>
              <dd className="text-sm leading-relaxed text-ink-muted">
                A lesson is whichever of those suits it. Listening practice does
                not need a video of somebody talking.
              </dd>
            </div>

            <div className="flex min-w-0 flex-col gap-2 px-5 text-center sm:even:border-s sm:even:border-line lg:[&+div]:border-s lg:[&+div]:border-line">
              <dt className="flex flex-col items-center gap-4 font-medium text-ink">
                <Captions aria-hidden="true" size={32} strokeWidth={1.5} className="text-ink" />
                Transcripts and subtitles
              </dt>
              <dd className="text-sm leading-relaxed text-ink-muted">
                Every spoken lesson is transcribed, so you can read along, search
                inside it, or follow without sound.
              </dd>
            </div>

            <div className="flex min-w-0 flex-col gap-2 px-5 text-center sm:even:border-s sm:even:border-line lg:[&+div]:border-s lg:[&+div]:border-line">
              <dt className="flex flex-col items-center gap-4 font-medium text-ink">
                <RotateCcw aria-hidden="true" size={32} strokeWidth={1.5} className="text-ink" />
                Progress that follows you
              </dt>
              <dd className="text-sm leading-relaxed text-ink-muted">
                Where you stopped is remembered per lesson, and picking up on
                another device continues from the same place.
              </dd>
            </div>

            <div className="flex min-w-0 flex-col gap-2 px-5 text-center sm:even:border-s sm:even:border-line lg:[&+div]:border-s lg:[&+div]:border-line">
              <dt className="flex flex-col items-center gap-4 font-medium text-ink">
                <BadgeCheck aria-hidden="true" size={32} strokeWidth={1.5} className="text-ink" />
                Reviewed, not just uploaded
              </dt>
              <dd className="text-sm leading-relaxed text-ink-muted">
                An administrator reads a course before it is published, and can
                send it back. That is the whole reason this catalogue is small.
              </dd>
            </div>
          </dl>
        </section>

        <FeaturedCourses courses={courses} />
      </div>
    </div>
  );
}
