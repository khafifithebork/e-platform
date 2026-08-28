import type { components } from "@/types/api";

/**
 * Searching the catalogue, from the browser.
 *
 * **A separate module from `courses.ts`, and not for tidiness.** That one runs
 * in Node during `next build` and must stop the build when it fails. This one
 * runs in a browser, after hydration, and must never break the page when it
 * fails — the catalogue is already on screen, and a failed search should cost
 * the visitor a message, not the content they were reading. Opposite failure
 * policies belong in different files.
 *
 * **Why this does not violate invariant 15.** The invariant forbids the
 * `(marketing)` group depending on a live API call *at request time* — that is
 * about server rendering: a page that fetches while responding cannot be
 * prerendered and, under B-lite, would cross the public internet from Workers
 * to Hetzner. This fetch happens in the visitor's browser, same-origin through
 * the Next rewrite, after the static HTML has already been delivered. The page
 * is still generated at build time; search is an enhancement on top of it.
 *
 * **Why not search the already-loaded catalogue in JavaScript.** M11 built
 * Postgres full-text search with weighted ranking — title A, skill areas B,
 * description C — plus trigram similarity so a typo still finds the course.
 * Substring matching in the browser is strictly worse at the thing search is
 * for, and it would make that work dead code.
 */

export type CourseSearchResults = components["schemas"]["CourseSearchResults"];

/**
 * Below this, searching is not useful and the request is skipped.
 *
 * One or two characters match nearly everything, so the results are noise and
 * the request is spent for nothing — and the endpoint is throttled at 30/min,
 * which is a budget worth not wasting on a visitor who has typed "s".
 */
export const MIN_QUERY_LENGTH = 2;

/**
 * The backend truncates at 200 characters and this matches it.
 *
 * Not a security control — the server enforces its own limit and strips
 * control characters, because a client-side cap is a suggestion. It is here so
 * a paste of a whole paragraph produces the same result the server would give
 * rather than a longer URL that means the same thing.
 */
export const MAX_QUERY_LENGTH = 200;

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "";

/** The search failed. Carries whether it is worth telling the user to retry. */
export class SearchFailed extends Error {
  constructor(
    message: string,
    readonly throttled: boolean = false,
  ) {
    super(message);
    this.name = "SearchFailed";
  }
}

/**
 * Ask the API for courses matching `query`.
 *
 * `signal` is not optional in practice: a search box fires a request per pause
 * in typing, and responses can arrive out of order. Without aborting the
 * previous one, a slow response to "spa" can land after a fast response to
 * "spanish" and overwrite the newer results with older ones — a bug that only
 * appears on a slow connection, which is to say on exactly the connections
 * nobody develops on.
 *
 * The query is sent through `URLSearchParams`, so a `&`, a `#` or a `%00` is
 * encoded rather than changing the shape of the request.
 */
export async function searchCourses(
  query: string,
  signal?: AbortSignal,
): Promise<CourseSearchResults> {
  const params = new URLSearchParams({ q: query.slice(0, MAX_QUERY_LENGTH) });

  let response: Response;
  try {
    response = await fetch(`${apiOrigin}/api/v1/catalogue/search/?${params}`, {
      signal,
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    // An abort is not a failure — it is this module working. Rethrown as-is so
    // the caller can ignore it rather than showing an error for a request it
    // cancelled itself.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new SearchFailed("Search is unavailable right now.");
  }

  if (response.status === 429) {
    // The endpoint is throttled at 30/min because a ranked query over a GIN
    // index is the most expensive thing an anonymous visitor can ask for. A
    // visitor who hits that deserves to be told what happened rather than
    // shown "no results", which is a lie about the catalogue.
    throw new SearchFailed("Too many searches. Wait a moment and try again.", true);
  }

  if (!response.ok) {
    throw new SearchFailed("Search is unavailable right now.");
  }

  return (await response.json()) as CourseSearchResults;
}
