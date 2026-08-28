import Link from "next/link";

import { CourseCard } from "@/components/catalogue/CourseCard";
import type { PublicCourse } from "@/lib/catalogue/courses";

/**
 * The most recently published courses, on the landing page.
 *
 * **Ordered here rather than trusted from the API.** The listing endpoint is
 * paginated by publication date, but "the order the endpoint happened to
 * return" is not a contract — and a landing page that silently reorders when
 * the backend changes its default ordering is the kind of change nobody traces
 * back. Sorted explicitly, with a stable tiebreak on slug so two courses
 * approved in the same second do not swap places between builds.
 *
 * **Renders nothing when there are no courses.** Not an empty grid, not a
 * heading over blank space — the section disappears. A launch-day landing page
 * with an empty "Recently published" band looks broken in a way that a shorter
 * page does not.
 */

/** Three, because it fills one row at every breakpoint the grid uses. */
export const FEATURED_LIMIT = 3;

export function FeaturedCourses({ courses }: { courses: PublicCourse[] }) {
  const featured = [...courses]
    .sort((a, b) => {
      const byDate = (b.published_at ?? "").localeCompare(a.published_at ?? "");
      return byDate !== 0 ? byDate : a.slug.localeCompare(b.slug);
    })
    .slice(0, FEATURED_LIMIT);

  if (featured.length === 0) return null;

  return (
    <section aria-labelledby="featured" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="featured" className="font-display text-2xl text-ink">
          Recently published
        </h2>
        <Link href="/courses" className="text-sm text-accent hover:text-accent-hover">
          {/*
           * "All courses" rather than a count. A number here would be accurate
           * only until the next publication, and a landing page that says "12
           * courses" while the catalogue holds 13 is wrong in the way nobody
           * checks.
           */}
          All courses
        </Link>
      </div>

      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {featured.map((course) => (
          <li key={course.slug}>
            <CourseCard course={course} />
          </li>
        ))}
      </ul>
    </section>
  );
}
