import type { MetadataRoute } from "next";

import { allPublishedCourses } from "@/lib/catalogue/courses";
import { PUBLIC_PATHS, siteUrl } from "@/lib/site";

/**
 * The sitemap, generated at build time from the same catalogue the pages use.
 *
 * **Empty when no origin is configured**, rather than filled with localhost URLs.
 * `src/lib/site.ts` explains why an absence is treated differently from a typo.
 * An empty sitemap is a valid sitemap; one that lists addresses nobody can reach
 * is a lie that looks like a feature.
 *
 * **Reading the catalogue rather than a hardcoded list** is the whole point: the
 * alternative is a second definition of "published", and the two disagree the day
 * somebody unpublishes a course. `allPublishedCourses` throws
 * `CatalogueUnavailable` when the API is unreachable, which stops the build —
 * correct here for the same reason it is correct on the catalogue page. A sitemap
 * that quietly loses every course is the dangerous outcome, because it deploys.
 *
 * **No `lastModified`, `changeFrequency` or `priority`.** The only date the
 * catalogue exposes is `published_at`, which is not when the course last changed,
 * and the other two are hints search engines have said for years they ignore.
 * Omitting them is honest; inventing a weekly cadence for a curated catalogue is
 * not. If the API ever exposes a real modification time, `lastModified` is worth
 * adding and nothing else here is.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const origin = siteUrl();
  if (origin === null) return [];

  const courses = await allPublishedCourses();

  return [
    ...PUBLIC_PATHS.map((path) => ({ url: new URL(path, origin).toString() })),
    ...courses.map((course) => ({
      url: new URL(`/courses/${encodeURIComponent(course.slug)}/`, origin).toString(),
    })),
  ];
}
