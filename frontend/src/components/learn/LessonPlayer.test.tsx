/**
 * The player, tested for the first time.
 *
 * Written at M7, 367 lines, and **never executed by a test or reached by a
 * user** — there was no runner until M15 T2 and no route to it until M16 T3.
 * Its arithmetic (`heartbeat.ts`) was tested at M15; everything that decides
 * *when* to run that arithmetic was not.
 *
 * Two of M16's abuse cases live here, and both are about destroying something
 * rather than failing to show it:
 *
 * - **4** — the player never reports progress for a lesson it could not load.
 *   A beat sent before the stored position arrives writes a playhead of zero
 *   over a real bookmark. The source says this was watched happening: *"a
 *   lesson resumed at 0:00 instead of 0:46, having just destroyed the one
 *   thing this page exists to prove."*
 * - **5** — progress survives a reload and resumes at the recorded position.
 *
 * Fake timers throughout, because the ticker runs on a one-second interval and
 * a beat is fifteen of them. Real time would make this suite take a minute and
 * flake.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LessonPlayer } from "@/components/learn/LessonPlayer";
import type { GatedLesson } from "@/lib/api/client";

const LESSON = {
  id: "11111111-1111-1111-1111-111111111111",
  course_slug: "spanish",
  section: "s1",
  slug: "intro",
  title: "Intro to Spanish",
  body: "Hola.",
  lesson_type: "VIDEO",
  position: 1,
  is_preview: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as unknown as GatedLesson;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function progress(overrides: Record<string, unknown> = {}) {
  return {
    lesson: LESSON.id,
    last_position_seconds: 0,
    watched_seconds: 0,
    completed_at: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** Routes each call the player makes, so one stub covers the whole load. */
function respond(overrides: { progress?: Response | (() => Response) } = {}) {
  return vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);

    if (path.includes("/progress/")) {
      const given = overrides.progress;
      if (given) return typeof given === "function" ? given() : given;
      return json(progress());
    }
    // No playback token and no transcript: both are optional on this page, and
    // the source says so — a 409 means the media is still transcoding, and a
    // missing transcript is ordinary. Refusing them keeps these tests about
    // the heartbeat rather than about video.
    return new Response("", { status: 404 });
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", respond());
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Advance the ticker by `seconds`, letting React flush between ticks. */
async function tick(seconds: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(seconds * 1000);
  });
}

function progressPuts() {
  return vi
    .mocked(globalThis.fetch)
    .mock.calls.filter(
      ([url, init]) =>
        String(url).includes("/progress/") && (init as RequestInit | undefined)?.method === "PUT",
    );
}

// The `init` element is optional in `fetch`'s own signature, and typing it as
// required here compiled under vitest — which does not type-check — and failed
// `tsc`. The suite was green while the build was broken.
function bodyOf(call: [input: string | URL | Request, init?: RequestInit]) {
  return JSON.parse(String(call[1]?.body));
}

describe("what it renders", () => {
  it("shows the lesson it was handed, without fetching it", async () => {
    render(<LessonPlayer lesson={LESSON} />);

    expect(await screen.findByRole("heading", { name: "Intro to Spanish" })).toBeInTheDocument();

    const lessonGets = vi
      .mocked(globalThis.fetch)
      .mock.calls.filter(([url]) => /\/lessons\/[^/]+\/$/.test(String(url)));

    expect(lessonGets).toHaveLength(0);
  });
});

describe("abuse case 5 — resuming", () => {
  it("starts at the recorded position, not at zero", async () => {
    vi.stubGlobal("fetch", respond({ progress: json(progress({ last_position_seconds: 46 })) }));

    render(<LessonPlayer lesson={LESSON} />);

    // Rendered as "At 0:46 · …", so a substring matcher rather than an exact one.
    expect(await screen.findByText(/At 0:46/)).toBeInTheDocument();
  });

  it("does not report that position straight back as new watching", async () => {
    // Restoring a bookmark is not watching. A beat that counted it would add
    // 46 seconds of watched time for a lesson nobody played.
    vi.stubGlobal("fetch", respond({ progress: json(progress({ last_position_seconds: 46 })) }));

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByText(/At 0:46/);
    await tick(20);

    expect(progressPuts()).toHaveLength(0);
  });
});

describe("abuse case 4 — nothing is reported before the bookmark is known", () => {
  /**
   * **Two guards enforce this, and only one of them is reachable today.**
   *
   * The source attributes it to `readyRef`: the ticker is installed on mount
   * and its cleanup reports a final beat, so a component that unmounted before
   * the progress fetch returned would write a playhead of zero over a real
   * bookmark. The comment says this was watched happening.
   *
   * Provoking it says otherwise. **Removing `readyRef` entirely leaves every
   * test here passing**, because `worthSending` refuses a beat with nothing
   * watched and nowhere reached — and nothing can be watched before the fetch
   * returns, since `loading` gates the play button out of the DOM.
   *
   * So `readyRef` is defence in depth rather than the deciding guard. It is
   * worth keeping — it does not depend on `worthSending` keeping its current
   * shape — but a test claiming to prove it would be a test that cannot fail.
   * What these two assert is the *property*, which is what matters.
   */
  it("sends no beat while the stored position is still loading", async () => {
    let release!: (value: Response) => void;
    vi.stubGlobal(
      "fetch",
      respond({ progress: () => new Response(null, { status: 204 }) }),
    );
    vi.mocked(globalThis.fetch).mockImplementation(
      (url) =>
        String(url).includes("/progress/")
          ? new Promise<Response>((resolve) => {
              release = resolve;
            })
          : Promise.resolve(new Response("", { status: 404 })),
    );

    const { unmount } = render(<LessonPlayer lesson={LESSON} />);
    await tick(40);
    unmount();

    expect(progressPuts()).toHaveLength(0);
    release(json(progress()));
  });

  it("sends nothing at all for a lesson whose progress never loaded", async () => {
    vi.stubGlobal("fetch", respond({ progress: () => new Response("", { status: 500 }) }));

    render(<LessonPlayer lesson={LESSON} />);
    await tick(40);

    expect(progressPuts()).toHaveLength(0);
  });
});

describe("the heartbeat", () => {
  it("reports nothing while paused", async () => {
    // `watchedSince` returns zero when not playing, and `worthSending`
    // suppresses a beat with nothing watched and nowhere reached. A learner
    // who opens a lesson and walks away has watched nothing.
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await tick(40);

    expect(progressPuts()).toHaveLength(0);
  });

  it("reports once a beat has elapsed while playing", async () => {
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(16);

    await waitFor(() => expect(progressPuts().length).toBeGreaterThan(0));
  });

  it("claims only the time actually spent playing", async () => {
    // The number completion is measured against (ADR-016 §2). Counting
    // wall-clock time would complete lessons nobody watched.
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await tick(20);
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(16);

    await waitFor(() => expect(progressPuts().length).toBeGreaterThan(0));
    const sent = bodyOf(progressPuts()[0]);

    expect(sent.watched_delta_seconds).toBeLessThanOrEqual(16);
    expect(sent.watched_delta_seconds).toBeGreaterThan(0);
  });

  it("does not re-claim the same stretch twice", async () => {
    // The unreported counter is cleared before the request, not after: a beat
    // that failed has still consumed that watching, and carrying it forward
    // would let a flaky connection accumulate an hour and claim it at once.
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(32);

    await waitFor(() => expect(progressPuts().length).toBeGreaterThanOrEqual(2));
    const total = progressPuts().reduce((sum, call) => sum + bodyOf(call).watched_delta_seconds, 0);

    expect(total).toBeLessThanOrEqual(32);
  });
});

describe("a subscription that lapses mid-lesson", () => {
  it("stops playing rather than continuing to show paid content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const path = String(url);
        if (path.includes("/progress/") && init?.method === "PUT") {
          return json(
            {
              type: "/problems/entitlement-denied",
              title: "Access denied",
              status: 403,
              detail: "Your subscription has ended.",
              errors: null,
              reason: "SUBSCRIPTION_EXPIRED",
            },
            403,
          );
        }
        if (path.includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(16);

    expect(await screen.findByRole("alert")).toHaveTextContent(/subscription has ended/i);
  });

  it("uses the shared refusal wording, not its own", async () => {
    // The table this component carried until T4 was keyed on codes the server
    // has never sent. `lib/entitlements/denial` is the one table now.
    const { REFUSALS } = await import("@/lib/entitlements/denial");

    expect(REFUSALS.SUBSCRIPTION_EXPIRED.title).toBe("Your subscription has ended");
  });
});
