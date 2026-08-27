/**
 * Reading the catalogue at build time.
 *
 * Two properties matter here and neither is visible from the page that calls
 * it:
 *
 * **Abuse case 6 — an unreachable API stops the build.** The failure to design
 * against is not a crash; it is a build that succeeds and deploys a site where
 * every course silently disappeared. That looks fine to everyone until a
 * learner asks where the catalogue went.
 *
 * **Pagination.** The endpoint is a DRF ViewSet with `PAGE_SIZE: 20`. Reading
 * one response works perfectly against a development database with one course
 * and truncates the catalogue at twenty the day the twenty-first is approved,
 * with no error anywhere — because a short list is a valid list. This was a
 * real bug in the first version of the module, found by looking at the live
 * response rather than by reasoning about the code.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CatalogueUnavailable, allPublishedCourses } from "@/lib/catalogue/courses";

function page(results: unknown[], next: string | null = null) {
  return new Response(JSON.stringify({ next, previous: null, results }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const A_COURSE = { slug: "spanish-a1", title: "Spanish", level: "A1" };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => page([A_COURSE])));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reading the catalogue", () => {
  it("returns the courses in the envelope", async () => {
    await expect(allPublishedCourses()).resolves.toHaveLength(1);
  });

  it("asks the API origin, not a relative path", async () => {
    // A relative URL has no meaning in Node during a build. It would throw
    // rather than fetch, which at least fails loudly — but the message would
    // point at the wrong thing entirely.
    await allPublishedCourses();

    const [url] = vi.mocked(globalThis.fetch).mock.calls[0];

    expect(String(url)).toMatch(/^https?:\/\/.+\/api\/v1\/catalogue\/courses\/$/);
  });

  it("sends no credentials", async () => {
    // The public catalogue is `AllowAny` with `authentication_classes = ()`.
    // A cookie here would make a public read look like an authenticated one,
    // and there is no session during a build anyway.
    await allPublishedCourses();

    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0];

    expect((init as RequestInit | undefined)?.credentials).toBeUndefined();
  });
});

describe("pagination", () => {
  it("follows next until there is none", async () => {
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(page([A_COURSE], "http://api.test/api/v1/catalogue/courses/?page=2"))
      .mockResolvedValueOnce(page([{ ...A_COURSE, slug: "spanish-b1" }]));

    await expect(allPublishedCourses()).resolves.toHaveLength(2);
  });

  it("makes one request per page and no more", async () => {
    // The twin. A loop that re-requests the same URL because it forgot to
    // advance would also return two courses — after an infinite number of
    // fetches.
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(page([A_COURSE], "http://api.test/api/v1/catalogue/courses/?page=2"))
      .mockResolvedValueOnce(page([{ ...A_COURSE, slug: "spanish-b1" }]));

    await allPublishedCourses();

    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(2);
  });

  it("follows the URL the API gave, rather than rebuilding one", async () => {
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(page([A_COURSE], "http://api.test/api/v1/catalogue/courses/?page=2"))
      .mockResolvedValueOnce(page([]));

    await allPublishedCourses();

    const [second] = vi.mocked(globalThis.fetch).mock.calls[1];

    expect(String(second)).toBe("http://api.test/api/v1/catalogue/courses/?page=2");
  });

  it("still reads a bare array, if pagination is ever switched off", async () => {
    // A settings change nobody would think to trace as far as this file.
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify([A_COURSE]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(allPublishedCourses()).resolves.toHaveLength(1);
  });
});

describe("abuse case 6 — the build stops rather than shipping an empty site", () => {
  it("throws when the API is unreachable", async () => {
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("fetch failed"));

    await expect(allPublishedCourses()).rejects.toBeInstanceOf(CatalogueUnavailable);
  });

  it("throws on a 500 rather than treating it as no courses", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      new Response("upstream exploded", { status: 500 }),
    );

    await expect(allPublishedCourses()).rejects.toBeInstanceOf(CatalogueUnavailable);
  });

  it("throws on a 404, which is what a renamed endpoint looks like", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(new Response("", { status: 404 }));

    await expect(allPublishedCourses()).rejects.toBeInstanceOf(CatalogueUnavailable);
  });

  it("says where it tried and what to do about it", async () => {
    // A build log that says "TypeError: fetch failed" sends somebody reading
    // Next's source. This is the one chance to say which service is down.
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("fetch failed"));

    await expect(allPublishedCourses()).rejects.toThrow(/API_ORIGIN|make dev/);
  });

  it("does not fall back to an empty catalogue", async () => {
    // Stated as its own test because it is the whole point, and because
    // "return []" is the change somebody makes at 5pm when the build is red
    // and the API is down.
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("fetch failed"));

    await expect(allPublishedCourses()).rejects.toThrow();
  });

  it("an empty catalogue from a healthy API is not an error", async () => {
    // The negative that keeps the case above honest. Zero courses is a real
    // state — the first day after launch — and failing the build on it would
    // mean the site cannot be deployed until somebody publishes something.
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(page([]));

    await expect(allPublishedCourses()).resolves.toEqual([]);
  });
});
