/**
 * The three boundaries ADR-031 added, and the property that matters most.
 *
 * **`verify:a11y` cannot see any of these.** It reads built HTML, and these render
 * only on failure — the same gap ADR-026 records for the dynamic lesson route. So
 * their structural properties are asserted here instead, which is the whole reason
 * this file exists rather than trusting the page-structure guard.
 *
 * Tested together because they are one decision. A reader asking "what happens
 * when a learner page throws" should find the answer in one file.
 */

import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GlobalError from "@/app/global-error";
import LearnerError from "@/app/(learner)/error";
import LessonLoading from "@/app/(learner)/courses/[slug]/lessons/[lessonSlug]/loading";

/**
 * The seam is mocked, not the SDK.
 *
 * `observability.test.ts` asserts `lib/observability/sentry.ts` is the only file
 * in `frontend/` that names the vendor, so a boundary reports through
 * `reportBoundaryError` and this is the thing to observe. Mocking the module
 * under test's *collaborator* rather than our own service layer — §6 forbids
 * mocking our service layer and asserting it was called, and that rule is about
 * pretending a behaviour happened; here the call itself **is** the behaviour
 * ADR-031 adds, and there is no other way to see it without a live DSN.
 */
const reportBoundaryError = vi.fn();
vi.mock("@/lib/observability/sentry", () => ({
  reportBoundaryError: (...args: unknown[]) => reportBoundaryError(...args),
}));

/**
 * A realistic error: a message carrying something that must not be rendered.
 *
 * The URL and the id are the point. `lib/observability/redact.ts` strips
 * addresses on the way *out* to Sentry; the visible page must not undo that by
 * printing them, and a bland `new Error("boom")` would not catch a page that
 * rendered `error.message`.
 */
function leakyError(): Error & { digest?: string } {
  const error = new Error(
    "Request to https://api.internal/lessons/9f2c-4a11 failed for learner@example.test",
  ) as Error & { digest?: string };
  error.digest = "3847562910";
  return error;
}

beforeEach(() => {
  reportBoundaryError.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the learner boundary", () => {
  it("never renders the error, its message, or its digest", () => {
    /**
     * **The assertion this file exists for.** Everything else here is structure;
     * this one is the security property. An error message can carry a URL, an id
     * or a fragment of a response, and a boundary is the easiest place in a
     * codebase to leak one — `{error.message}` is what a hurried implementation
     * writes, and it looks helpful.
     */
    const { container } = render(<LearnerError error={leakyError()} reset={vi.fn()} />);

    expect(container.innerHTML).not.toContain("api.internal");
    expect(container.innerHTML).not.toContain("9f2c-4a11");
    expect(container.innerHTML).not.toContain("learner@example.test");
    expect(container.innerHTML).not.toContain("3847562910");
  });

  it("reports exactly once", () => {
    render(<LearnerError error={leakyError()} reset={vi.fn()} />);

    expect(reportBoundaryError).toHaveBeenCalledTimes(1);
  });

  it("says that recent progress may not have been saved", () => {
    /**
     * Not cosmetic. `LessonPlayer` reports progress on an interval and a final
     * beat on unmount; a render error takes it down and whatever that beat had
     * not sent is gone. A page implying everything is fine would be worse than
     * one admitting it does not know.
     */
    render(<LearnerError error={leakyError()} reset={vi.fn()} />);

    expect(screen.getByText(/progress may not have been saved/i)).toBeVisible();
  });

  it("offers a retry that re-renders the segment", async () => {
    const reset = vi.fn();
    const { default: userEvent } = await import("@testing-library/user-event");
    render(<LearnerError error={leakyError()} reset={reset} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));

    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("titles itself once and offers a way out", () => {
    render(<LearnerError error={leakyError()} reset={vi.fn()} />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    // An authenticated destination, because anyone reaching this is signed in.
    expect(screen.getByRole("link", { name: /my courses/i })).toHaveAttribute(
      "href",
      "/my-courses",
    );
  });
});

describe("the global boundary", () => {
  it("never renders the error either", () => {
    const { container } = render(<GlobalError error={leakyError()} />);

    expect(container.innerHTML).not.toContain("api.internal");
    expect(container.innerHTML).not.toContain("learner@example.test");
    expect(container.innerHTML).not.toContain("3847562910");
  });

  it("reports exactly once", () => {
    render(<GlobalError error={leakyError()} />);

    expect(reportBoundaryError).toHaveBeenCalledTimes(1);
  });

  it("stands alone: one heading, one landmark, and a link that needs no JavaScript", () => {
    /**
     * This replaces the document, so it is the whole page — it needs its own
     * `<main>` and `<h1>`, which no layout provides. And the way out is an `<a>`
     * rather than a `reset()` button: when the root layout is what failed,
     * re-rendering the same tree is unlikely to help, and an anchor works
     * without the JavaScript that may itself be the problem.
     */
    render(<GlobalError error={leakyError()} />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("link", { name: /home page/i })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("depends on no design-system token, because it may be what failed", () => {
    /**
     * The constraint that makes this file plain. `global-error.tsx` replaces the
     * document, so `globals.css` and the `body` styling are not guaranteed to
     * have loaded — and the scenario it exists for is the root layout failing,
     * which is where a stylesheet or a provider is the likely culprit.
     *
     * Asserted by source, because "did not use a token" is not observable in a
     * rendered tree that never had the stylesheet.
     */
    const source = readFileSync(
      join(import.meta.dirname, "global-error.tsx"),
      "utf8",
    ).replace(/\/\*[\s\S]*?\*\//g, "");

    /**
     * `var(--` rather than a list of token prefixes. The first version of this
     * checked `--color-`, `--radius-` and `--shadow-`, and **passed when the
     * provocation substituted `var(--font-display)`** — a token it had not
     * thought to name. A guard enumerating the things it knows about will always
     * miss the next one; the property is "reaches for no custom property at all",
     * so that is what it now asserts.
     */
    expect(source).not.toMatch(/var\(--/);
    expect(source).not.toMatch(/PageTitle|SiteShell|buttonStyles|className=/);
  });
});

describe("the lesson loading state", () => {
  it("announces itself politely, with words", () => {
    // Not a bare spinner. ADR-026: the rest of the page is empty while this
    // resolves, so a screen-reader user otherwise gets no signal at all.
    render(<LessonLoading />);

    const status = screen.getByText(/loading the lesson/i);
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("reserves space so the page does not jump when the lesson arrives", () => {
    // The placeholder is `aria-hidden`: it stands for something that has not
    // loaded, and announcing it would be describing furniture.
    const { container } = render(<LessonLoading />);

    const placeholder = container.querySelector('[aria-hidden="true"]');
    expect(placeholder).not.toBeNull();
    expect(placeholder?.className).toContain("aspect-video");
  });
});
