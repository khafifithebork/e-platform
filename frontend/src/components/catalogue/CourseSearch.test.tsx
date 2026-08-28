/**
 * The search box.
 *
 * **Abuse case 4** — a query arrives from what the visitor typed and is
 * displayed back to them. React escapes by default and nothing here uses
 * `dangerouslySetInnerHTML`, so this is a property to pin rather than a bug to
 * fix: the test is what notices the day somebody reaches for it to highlight a
 * matched term, which is the obvious reason to want raw HTML on a search page.
 *
 * **The throttle is a design constraint, not a detail.** The endpoint allows
 * 30/min because a ranked query over a GIN index is the most expensive thing
 * an anonymous visitor can ask this service to do. A request per keystroke
 * exhausts that in eight characters, so the debounce is load-bearing and is
 * tested as such.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { CourseSearch } from "@/components/catalogue/CourseSearch";
import type { CourseSearchResults } from "@/lib/catalogue/search";

function payload(courses: unknown[] = [], extra: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      results: courses,
      count: courses.length,
      limit: 50,
      truncated: false,
      ...extra,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

// Typed explicitly rather than `ReturnType<typeof vi.fn>`: that resolves to a
// mock with no call signature, so passing it as a prop is a type error — which
// `tsc --noEmit` catches and `vitest` does not, because it never type-checks.
let onResults: Mock<(results: CourseSearchResults | null) => void>;
let onQueryChange: Mock<(query: string) => void>;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => payload()));
  onResults = vi.fn();
  onQueryChange = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderSearch() {
  return render(<CourseSearch onResults={onResults} onQueryChange={onQueryChange} />);
}

/** Types without the per-keystroke delay `userEvent` adds by default. */
const type = (element: HTMLElement, text: string) =>
  userEvent.setup({ delay: null }).type(element, text);

describe("the control", () => {
  it("is labelled", () => {
    // A bare input with a placeholder is not labelled: a placeholder vanishes
    // on focus and is not a name in the accessibility tree.
    renderSearch();

    expect(screen.getByLabelText("Search courses")).toBeInTheDocument();
  });

  it("is a search input, so browsers offer a clear button", () => {
    renderSearch();

    expect(screen.getByLabelText("Search courses")).toHaveAttribute("type", "search");
  });

  it("describes itself with the status line", () => {
    // So the result count and any error are announced as part of this field
    // rather than as loose text elsewhere on the page.
    renderSearch();

    const input = screen.getByLabelText("Search courses");
    const describedBy = input.getAttribute("aria-describedby");

    expect(document.getElementById(describedBy!)).toHaveAttribute("aria-live", "polite");
  });
});

describe("the debounce", () => {
  it("does not fire a request per keystroke", async () => {
    // Eight characters at one request each exhausts a 30/min budget, and the
    // visitor gets 429 for the rest of the minute.
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "spanish");

    expect(vi.mocked(globalThis.fetch)).not.toHaveBeenCalled();
  });

  it("fires once after typing stops", async () => {
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "spanish");
    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1));
  });

  it("searches for the whole word, not a prefix", async () => {
    // The twin of the test above. A debounce that fired on the first keystroke
    // and then cancelled would also end with one call — for "s".
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "spanish");
    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());

    expect(String(vi.mocked(globalThis.fetch).mock.calls[0][0])).toContain("q=spanish");
  });

  it("does not search a single character", async () => {
    // One character matches nearly everything, so the results are noise and
    // the request is spent for nothing.
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "s");
    await new Promise((resolve) => setTimeout(resolve, 600));

    expect(vi.mocked(globalThis.fetch)).not.toHaveBeenCalled();
  });
});

describe("clearing the box", () => {
  it("returns the visitor to the full catalogue", async () => {
    // Rather than leaving the last results stranded under an empty search box.
    renderSearch();
    const input = screen.getByLabelText("Search courses");

    await type(input, "spanish");
    await waitFor(() => expect(onResults).toHaveBeenCalled());
    await userEvent.setup({ delay: null }).clear(input);

    await waitFor(() => expect(onResults).toHaveBeenLastCalledWith(null));
  });

  it("tells the parent the query is empty", async () => {
    renderSearch();
    const input = screen.getByLabelText("Search courses");

    await type(input, "spanish");
    await userEvent.setup({ delay: null }).clear(input);

    expect(onQueryChange).toHaveBeenLastCalledWith("");
  });
});

describe("failure", () => {
  it("says the search failed without taking the page with it", async () => {
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "spanish");

    await waitFor(() =>
      expect(screen.getByText(/search is unavailable/i)).toBeInTheDocument(),
    );
  });

  it("hands the parent null, so the catalogue stays on screen", async () => {
    // A failed search must cost the visitor a message, not the content they
    // were already reading.
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "spanish");

    await waitFor(() => expect(onResults).toHaveBeenLastCalledWith(null));
  });

  it("explains a 429 rather than showing nothing", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(new Response("", { status: 429 }));
    renderSearch();

    await type(screen.getByLabelText("Search courses"), "spanish");

    await waitFor(() => expect(screen.getByText(/too many searches/i)).toBeInTheDocument());
  });
});

describe("out-of-order responses", () => {
  it("does not let a slow earlier search overwrite a newer one", async () => {
    /**
     * The bug this component's `AbortController` exists for, driven end to
     * end rather than asserted by checking a signal was passed.
     *
     * A visitor types "spa", pauses, types "nish". Two requests go out. The
     * first is slow. Without cancellation its answer lands second and the
     * visitor sees results for "spa" while the box says "spanish" — and it
     * only happens on a slow connection, which is where nobody develops.
     *
     * `fetch` is stubbed to honour the abort signal, the way a real one does.
     * A stub that ignored it would make this test pass against a component
     * with no cancellation at all.
     */
    vi.mocked(globalThis.fetch).mockImplementation((_url, init) => {
      const signal = (init as RequestInit | undefined)?.signal;
      const slow = String(_url).includes("q=spa&") || String(_url).endsWith("q=spa");

      return new Promise((resolve, reject) => {
        const timer = setTimeout(
          () => resolve(payload([{ slug: slow ? "STALE" : "FRESH" }])),
          // The slow one must still be in flight when the second search
          // starts, or there is no race to test. An earlier version used
          // 200ms: the "spa" response resolved at t=600ms, before the
          // "spanish" request was even made at t=900ms, so it was simply the
          // first search finishing — and the test failed for a reason that
          // said nothing about cancellation.
          slow ? 1500 : 10,
        );
        signal?.addEventListener("abort", () => {
          clearTimeout(timer);
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    });

    renderSearch();
    const input = screen.getByLabelText("Search courses");

    await type(input, "spa");
    // Long enough for the debounce to fire the first request, short enough
    // that its slow response has not arrived.
    await new Promise((resolve) => setTimeout(resolve, 500));
    await type(input, "nish");

    // Long enough for the aborted request's original deadline to pass, so a
    // component without cancellation has had every chance to deliver it.
    await waitFor(() => expect(onResults).toHaveBeenCalledWith(expect.anything()));
    await new Promise((resolve) => setTimeout(resolve, 1800));

    const delivered = onResults.mock.calls
      .map(([value]) => value)
      .filter((value) => value !== null);

    expect(delivered.every((value) => value.results[0]?.slug !== "STALE")).toBe(true);
  });
});

describe("abuse case 4 — the query is not reflected as markup", () => {
  it("keeps a script tag as text in the input", async () => {
    renderSearch();
    const hostile = '<script>alert(1)</script>';

    await type(screen.getByLabelText("Search courses"), hostile);

    expect(screen.getByLabelText("Search courses")).toHaveValue(hostile);
    expect(document.querySelector("script")).toBeNull();
  });

  it("uses no dangerouslySetInnerHTML anywhere in the search path", async () => {
    // Structural, and aimed at a specific future change: highlighting the
    // matched term in a result is the obvious reason somebody reaches for raw
    // HTML on a search page, and the query is the thing they would interpolate.
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");

    const files = [
      join(process.cwd(), "src", "components", "catalogue", "CourseSearch.tsx"),
      join(process.cwd(), "src", "components", "catalogue", "CourseCatalogue.tsx"),
      join(process.cwd(), "src", "components", "catalogue", "CourseCard.tsx"),
    ];

    const offenders = files.filter((path) =>
      /dangerouslySetInnerHTML/.test(readFileSync(path, "utf8")),
    );

    expect(offenders).toEqual([]);
  });
});
