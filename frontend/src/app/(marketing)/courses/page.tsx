import type { Metadata } from "next";

import { CourseCatalogue } from "@/components/catalogue/CourseCatalogue";
import { allPublishedCourses, catalogueLanguages } from "@/lib/catalogue/courses";

export const metadata: Metadata = {
  title: "Courses",
  description: "Every published course, by language and level.",
};

/**
 * The catalogue.
 *
 * **Static, and the data is read at build time.** Invariant 15. The two
 * requests below run during `next build` in CI, where Django is reachable
 * locally; the generated HTML carries every course, so a visitor's page load
 * touches no API at all.
 *
 * **No `searchParams`.** Filters would obviously be query parameters, and
 * reading them here would opt this route into dynamic rendering — which is
 * precisely what invariant 15 forbids. The filters are client-side over data
 * already in the page instead, and the structural test on this route group
 * now looks for `searchParams` by name so the obvious mistake is a failing
 * test rather than a quietly dynamic route.
 *
 * **Fetched in parallel.** They do not depend on each other, and awaiting them
 * in sequence would make every build pay two round trips where one will do.
 */
export default async function CoursesPage() {
  const [courses, languages] = await Promise.all([
    allPublishedCourses(),
    catalogueLanguages(),
  ]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <h1 className="font-display text-4xl tracking-tight text-ink">Courses</h1>
        <p className="max-w-xl text-ink-muted">
          Every course here was reviewed and approved before it was published.
        </p>
      </header>

      <CourseCatalogue courses={courses} languages={languages} />
    </div>
  );
}
