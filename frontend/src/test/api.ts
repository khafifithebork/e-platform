import { vi } from "vitest";

/**
 * Stubbing `fetch` for the four pages that post to the auth API.
 *
 * **Routing by path rather than returning one response.** Every unsafe request
 * goes through `ensureCsrfToken` first, which fetches `/auth/csrf/` when the
 * cookie is absent — and in jsdom it always is. A test that stubs `fetch` with
 * a single `mockResolvedValue` therefore hands the CSRF probe the response it
 * meant for the form, and the form's own request gets the same body a second
 * time. That failure reads as "the page ignored the error" rather than "the
 * test answered the wrong request", which is why this is a helper and not four
 * copies of the same three lines.
 *
 * `AuthMenu.test.tsx` and `SiteNavTree.test.tsx` do not need this: they only
 * read `/auth/me/`, a GET, which never asks for a token.
 */

/** A JSON response, the way the API sends them. */
export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * A DRF Problem Details refusal (ADR-004).
 *
 * `detail` is the caller's to choose on purpose. The tests that matter most
 * here pass two different strings and assert the page shows whichever it was
 * given — a page that hardcoded a friendlier message would satisfy a single
 * fixed fixture.
 */
export function refusal(
  status: number,
  detail: string,
  errors: Record<string, string[]> | null = null,
): Response {
  return json({ type: "about:blank", title: "Request failed", status, detail, errors }, status);
}

/** What the API returns for an accepted auth write: a bare confirmation. */
export function accepted(): Response {
  return json({ detail: "Accepted." });
}

/**
 * Install a `fetch` that answers the CSRF probe and routes everything else to
 * `answer`. Returns the mock, so a test can inspect what was sent.
 */
export function stubApi(answer: (path: string, init: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
      const path = String(input);
      if (path.endsWith("/auth/csrf/")) return new Response(null, { status: 204 });
      return answer(path, init);
    },
  );

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The paths the app requested, with the CSRF probe left out. */
export function requestedPaths(fetchMock: ReturnType<typeof stubApi>): string[] {
  return fetchMock.mock.calls
    .map(([input]) => String(input))
    .filter((path) => !path.endsWith("/auth/csrf/"));
}

/** The bodies the app posted to `path`, parsed. */
export function postedTo(fetchMock: ReturnType<typeof stubApi>, path: string): unknown[] {
  return fetchMock.mock.calls
    .filter(([input]) => String(input).endsWith(path))
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}
