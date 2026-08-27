import type { components } from "@/types/api";

/**
 * Reading the public catalogue at build time.
 *
 * **Build time, never request time.** CLAUDE.md invariant 15: the
 * `(marketing)` group must not depend on a live API call while serving a
 * request. Everything here runs during `next build`, in CI, where Django is
 * reachable over the job's own network — and the generated HTML carries the
 * courses, so a visitor's page load touches no API at all.
 *
 * That is also what keeps CLAUDE.md §11 #5 moot. Under B-lite, Next runs on
 * Cloudflare Workers and Django on Hetzner with no private network between
 * them; a request-time fetch would cross the public internet and need its own
 * authentication. A build-time fetch happens in CI, where both are local.
 *
 * Kept out of `app/(marketing)/` deliberately. The structural test on that
 * directory forbids `fetch` outright, which is the blunt version of the real
 * rule — and the layering it enforces matches the backend's: data access has
 * its own module, pages render.
 */

export type PublicCourse = components["schemas"]["PublicCourse"];
export type PublicCourseDetail = components["schemas"]["PublicCourseDetail"];
export type PublicSection = components["schemas"]["PublicSection"];
export type PublicLesson = components["schemas"]["PublicLesson"];
export type Language = components["schemas"]["Language"];

/**
 * Where Django is during the build.
 *
 * The same variable `next.config.ts` uses for its rewrite, so there is one
 * answer to "where is the API" rather than two that can disagree. The
 * localhost default is for a developer with `make dev` running; CI sets it
 * explicitly.
 */
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

/**
 * Thrown when the catalogue cannot be read.
 *
 * Its own class so the failure is unmistakable in a build log. A build that
 * cannot reach the API must stop.
 */
export class CatalogueUnavailable extends Error {
  constructor(detail: string) {
    super(
      `Could not read the catalogue from ${apiOrigin}: ${detail}\n` +
        `The public pages are generated at build time, so this build cannot continue. ` +
        `Start the API (make dev) or set API_ORIGIN.`,
    );
    this.name = "CatalogueUnavailable";
  }
}

/**
 * The API answered 404.
 *
 * Extends `CatalogueUnavailable` deliberately: on a list endpoint a 404 means
 * somebody renamed a route and the build should stop, which is the inherited
 * behaviour. On a single course it means that course is no longer published,
 * which is a page that should 404 rather than a build that should fail.
 */
export class CatalogueNotFound extends CatalogueUnavailable {
  constructor(detail: string) {
    super(detail);
    this.name = "CatalogueNotFound";
  }
}

/** DRF's paginated envelope. Cursor-free — this API uses page numbers. */
interface Page<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}

async function readCatalogue<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      // No credentials. The public catalogue is `AllowAny` with
      // `authentication_classes = ()`, and sending a cookie the build does not
      // have would only make this look like an authenticated call.
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    // **Abuse case 6.** A network failure must stop the build, not produce a
    // site with an empty catalogue. The empty site is the dangerous outcome:
    // it deploys, it looks fine, and every course silently disappeared.
    throw new CatalogueUnavailable(cause instanceof Error ? cause.message : String(cause));
  }

  if (response.status === 404) {
    // A subclass, so every existing caller that treats 404 as a broken
    // catalogue still does. Only the code that asks for one course by slug
    // cares about the difference, and for that one it is the whole question:
    // "this course is not published" and "the API is broken" want opposite
    // responses, and a single error type cannot tell them apart.
    throw new CatalogueNotFound(`${response.status} ${response.statusText}`);
  }

  if (!response.ok) {
    throw new CatalogueUnavailable(`${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

/**
 * Read every page, not just the first.
 *
 * **This is a correction, and the bug it fixes is the quiet kind.** The first
 * version of this module read one response and returned `payload.results`.
 * The catalogue endpoint is a DRF ViewSet with `PAGE_SIZE: 20`, so that would
 * have worked perfectly on a development database with one course and silently
 * published a catalogue of exactly twenty the day the twenty-first was
 * approved — with no error anywhere, because a truncated list is a valid list.
 *
 * Found by looking at the live response rather than by reasoning about the
 * code: it returns `{next, previous, results}`, and `next` is the whole story.
 *
 * The bare-array branch stays because it costs one line and covers pagination
 * being switched off centrally, which is a settings change nobody would think
 * to trace as far as this file.
 */
async function readAllPages<T>(path: string): Promise<T[]> {
  let url: string | null = `${apiOrigin}/api/v1/catalogue${path}`;
  const everything: T[] = [];

  while (url) {
    const payload: T[] | Page<T> = await readCatalogue<T[] | Page<T>>(url);

    if (Array.isArray(payload)) return payload;

    everything.push(...payload.results);
    // `next` is an absolute URL built by DRF from the request it saw. That is
    // the API's own origin, which is what we asked for, so it is followed as
    // given rather than reassembled here.
    url = payload.next;
  }

  return everything;
}

/**
 * Every published course, for the listing page.
 *
 * Returns the whole catalogue rather than a filtered slice, because the
 * filtering happens in the browser against data already in the page — a
 * filter that refetched would be a request-time API call, which is the thing
 * invariant 15 forbids.
 *
 * That works because this is a curated catalogue: courses are admin-approved,
 * so the count is in the tens, not the millions. **If it ever is not**, the
 * answer is filter-as-route-segment with `generateStaticParams`, not a
 * request-time query — and that decision belongs to whoever notices the page
 * weight, not to this comment.
 */
export async function allPublishedCourses(): Promise<PublicCourse[]> {
  return readAllPages<PublicCourse>("/courses/");
}

/** The languages that have published courses, for the filter control. */
export async function catalogueLanguages(): Promise<Language[]> {
  return readAllPages<Language>("/languages/");
}

/**
 * Every published slug, for `generateStaticParams`.
 *
 * Reads the same listing the catalogue page does. That is one extra request
 * per build rather than a dedicated slugs endpoint, and it is the right trade:
 * a second endpoint would be a second definition of "published", and the two
 * would eventually disagree about a course somebody just unpublished.
 */
export async function publishedCourseSlugs(): Promise<string[]> {
  const courses = await allPublishedCourses();
  return courses.map((course) => course.slug);
}

/**
 * One course, with its curriculum and its related courses.
 *
 * `related` is embedded in this response rather than fetched separately — the
 * serializer says why, and says it in these terms: public pages are statically
 * generated, so a second round trip is paid at build time for data the first
 * response already knows.
 *
 * Throws `CatalogueNotFound` when the course is not published. The caller
 * turns that into a 404; anything else is still a build-stopping failure.
 */
export async function publishedCourse(slug: string): Promise<PublicCourseDetail> {
  return readCatalogue<PublicCourseDetail>(
    `${apiOrigin}/api/v1/catalogue/courses/${encodeURIComponent(slug)}/`,
  );
}
