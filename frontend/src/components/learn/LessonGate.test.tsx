/**
 * Resolving two slugs to a lesson, and what happens when it does not.
 *
 * Three of M16's abuse cases meet here, and each is about what a refusal shows
 * rather than what a success does:
 *
 * - **1** — a signed-out visitor reaching a gated lesson is told, not shown it.
 * - **3** — a preview lesson plays for somebody with no account at all. The
 *   resolver allows it before it looks at a user, and the UI must not add a
 *   check the backend does not have.
 * - **7** — no page renders lesson content it was refused. A 403 is not an
 *   empty player.
 *
 * The player itself is stubbed. It is 367 lines, it owns its own network
 * traffic, and T6 is the task that tests it; what matters here is whether it
 * is reached at all, and with what.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LessonGate } from "@/components/learn/LessonGate";

vi.mock("@/components/learn/LessonPlayer", () => ({
  LessonPlayer: ({ lessonId }: { lessonId: string }) => (
    <div data-testid="player">player for {lessonId}</div>
  ),
}));

const LESSON = {
  id: "11111111-1111-1111-1111-111111111111",
  course_slug: "spanish",
  section: "s1",
  slug: "intro",
  title: "Intro",
  body: "SECRET-LESSON-BODY",
  lesson_type: "VIDEO",
  position: 1,
  is_preview: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function problem(status: number, extra: Record<string, unknown> = {}) {
  return json(
    {
      type: "/problems/entitlement-denied",
      title: "Access denied",
      status,
      detail: "You are not entitled to this lesson.",
      errors: null,
      ...extra,
    },
    status,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => json(LESSON)));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderGate() {
  return render(<LessonGate courseSlug="spanish" lessonSlug="intro" />);
}

describe("resolving the lesson", () => {
  it("asks for it at the course-scoped URL", async () => {
    // architecture.md §6.2, and the route the redundant `course` foreign key
    // was added for.
    renderGate();

    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());
    const [url] = vi.mocked(globalThis.fetch).mock.calls[0];

    expect(String(url)).toBe("/api/v1/courses/spanish/lessons/intro/");
  });

  it("hands the resolved id to the player", async () => {
    // The player addresses progress, completion, playback and the transcript
    // by id. Passing it the slug would break all four silently.
    renderGate();

    expect(await screen.findByTestId("player")).toHaveTextContent(LESSON.id);
  });

  it("offers a way back to the course", async () => {
    renderGate();
    await screen.findByTestId("player");

    expect(screen.getByRole("link", { name: /back to the course/i })).toHaveAttribute(
      "href",
      "/courses/spanish",
    );
  });

  it("says something while it is loading", () => {
    // The page is otherwise empty until this resolves, and a live region is
    // the only signal a screen-reader user gets that anything is happening.
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise<Response>(() => {}));

    renderGate();

    expect(screen.getByText(/loading the lesson/i)).toHaveAttribute("aria-live", "polite");
  });
});

describe("abuse case 3 — a preview plays without an account", () => {
  it("renders the player for an anonymous visitor", async () => {
    // The resolver's first branch allows a preview before it asks who is
    // calling. A gate that required a session here would refuse people the
    // backend deliberately admits.
    renderGate();

    expect(await screen.findByTestId("player")).toBeInTheDocument();
  });
});

describe("abuse cases 1 and 7 — a refusal shows no lesson", () => {
  it("does not render the player when access is refused", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(problem(403, { reason: "NO_SUBSCRIPTION" }));

    renderGate();
    await screen.findByRole("heading", { name: /do not have access/i });

    expect(screen.queryByTestId("player")).not.toBeInTheDocument();
  });

  it("shows the reason the server gave", async () => {
    // `resolve_access` returns a reason, never a bare boolean — invariant 3.
    // Six of them exist; T4 gives each its own wording, and until then showing
    // the code is honest rather than inventing a message for all six.
    vi.mocked(globalThis.fetch).mockResolvedValue(problem(403, { reason: "NO_SUBSCRIPTION" }));

    renderGate();

    expect(await screen.findByText("NO_SUBSCRIPTION")).toBeInTheDocument();
  });

  it("leaks no lesson body in a refusal", async () => {
    // The property that outlives any particular wording. A 403 whose payload
    // still carried the body would be a paywall in name only — and this
    // asserts the *page* shows none of it, whatever the API sent.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      problem(403, { reason: "NO_SUBSCRIPTION", body: LESSON.body }),
    );

    renderGate();
    await screen.findByRole("heading", { name: /do not have access/i });

    expect(document.body.textContent).not.toContain("SECRET-LESSON-BODY");
  });

  it("points at what a subscription covers", async () => {
    // Not at a checkout: there is no self-serve subscription and no price
    // (§11 #1). `/pricing` says so plainly, which is the honest destination.
    vi.mocked(globalThis.fetch).mockResolvedValue(problem(403, { reason: "NO_SUBSCRIPTION" }));

    renderGate();

    expect(await screen.findByRole("link", { name: /what a subscription covers/i })).toHaveAttribute(
      "href",
      "/pricing",
    );
  });
});

describe("a lesson that is not there", () => {
  it("says so rather than showing a refusal", async () => {
    // The API conflates "no such lesson" with "the course is not published" on
    // purpose — §6.3, because a 403 would confirm an unreleased course exists.
    // The UI must not undo that by guessing which one it was.
    vi.mocked(globalThis.fetch).mockResolvedValue(new Response("", { status: 404 }));

    renderGate();

    expect(await screen.findByRole("heading", { name: /not here/i })).toBeInTheDocument();
  });

  it("does not render the player", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(new Response("", { status: 404 }));

    renderGate();
    await screen.findByRole("heading", { name: /not here/i });

    expect(screen.queryByTestId("player")).not.toBeInTheDocument();
  });
});

describe("something else going wrong", () => {
  it("is not reported as a refusal", async () => {
    // Telling somebody they lack access when the server is down sends them to
    // a pricing page to solve an outage.
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));

    renderGate();

    expect(await screen.findByRole("heading", { name: /could not be loaded/i })).toBeInTheDocument();
  });

  it("still offers a way out", async () => {
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));

    renderGate();
    await screen.findByRole("heading", { name: /could not be loaded/i });

    expect(screen.getByRole("link", { name: /back to the course/i })).toBeInTheDocument();
  });
});
