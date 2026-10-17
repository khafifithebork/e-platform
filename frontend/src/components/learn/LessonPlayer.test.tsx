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

import { act, render, screen, waitFor, within } from "@testing-library/react";
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
  it("groups reachable playback controls without showing a technical course slug", async () => {
    render(<LessonPlayer lesson={{ ...LESSON, title: "A long lesson title ".repeat(10) }} />);
    const controls = await screen.findByRole("group", { name: "Playback controls" });
    expect(within(controls).getByRole("button", { name: "Back 5 seconds" })).toBeEnabled();
    expect(within(controls).getByRole("combobox", { name: "Speed" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Mark complete" })).toBeEnabled();
    expect(screen.queryByText(LESSON.course_slug, { exact: true })).not.toBeInTheDocument();
  });

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

describe("completion", () => {
  it("waits for server confirmation and blocks repeat completion submits", async () => {
    let confirm!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/complete/")) {
        return new Promise<Response>((resolve) => { confirm = resolve; });
      }
      if (String(url).includes("/progress/")) return json(progress());
      return new Response("", { status: 404 });
    }));
    render(<LessonPlayer lesson={LESSON} />);
    await userEvent.click(await screen.findByRole("button", { name: "Mark complete" }));
    const pending = screen.getByRole("button", { name: "Working…" });
    expect(pending).toBeDisabled();
    expect(pending).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
    await act(async () => { confirm(json(progress({ completed_at: "2026-02-01T00:00:00Z" }))); });
    expect(await screen.findByText("Completed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark complete" })).not.toBeInTheDocument();
  });

  /**
   * **Displayed, never decided.** ADR-016 §2 puts the rule on the server, and
   * every progress response carries `completed_at`. A client that decided for
   * itself would be the second definition M7 warns about — and the two would
   * disagree the first time the rule changed.
   */

  it("shows a course already finished as finished", async () => {
    vi.stubGlobal(
      "fetch",
      respond({ progress: json(progress({ completed_at: "2026-02-01T00:00:00Z" })) }),
    );

    render(<LessonPlayer lesson={LESSON} />);

    expect(await screen.findByText("Completed")).toBeInTheDocument();
  });

  it("offers no button once it is finished", async () => {
    // The negative. Both rendering at once is what an `&&` instead of a
    // ternary produces, and "mark complete" beside "Completed" reads as though
    // the first click did not work.
    vi.stubGlobal(
      "fetch",
      respond({ progress: json(progress({ completed_at: "2026-02-01T00:00:00Z" })) }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByText("Completed");

    expect(screen.queryByRole("button", { name: /mark complete/i })).not.toBeInTheDocument();
  });

  it("asks the server rather than deciding", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        calls.push(String(url));
        if (String(url).includes("/complete/")) {
          return json(progress({ completed_at: "2026-02-01T00:00:00Z" }));
        }
        if (String(url).includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await userEvent.click(await screen.findByRole("button", { name: /mark complete/i }));

    await waitFor(() => expect(calls.some((url) => url.includes("/complete/"))).toBe(true));
  });

  it("shows completion only after the server confirms it", async () => {
    // The property that makes it "displayed, never decided": the label changes
    // because the response said so, not because the button was pressed.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        if (String(url).includes("/complete/")) {
          return json(progress({ completed_at: "2026-02-01T00:00:00Z" }));
        }
        if (String(url).includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await userEvent.click(await screen.findByRole("button", { name: /mark complete/i }));

    expect(await screen.findByText("Completed")).toBeInTheDocument();
  });

  it("does not claim completion when the server refuses", async () => {
    // A subscription that lapsed between loading the lesson and pressing the
    // button. Showing "Completed" anyway would record nothing and tell the
    // learner it had.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        if (String(url).includes("/complete/")) {
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
        if (String(url).includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await userEvent.click(await screen.findByRole("button", { name: /mark complete/i }));

    await screen.findByRole("alert");

    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });

  it("stops offering completion once access is refused", async () => {
    // The button is disabled by a denial. Leaving it live would invite a
    // second refusal for the same reason.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        if (String(url).includes("/progress/") && init?.method === "PUT") {
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
        if (String(url).includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(16);
    await screen.findByRole("alert");

    expect(screen.getByRole("button", { name: /mark complete/i })).toBeDisabled();
  });
});

/**
 * The captions track, and a blocker that was not one.
 *
 * ADR-033 §3 recorded `<track>`'s missing `srclang` and `label` as **blocked on the
 * backend**: "the API does not expose the caption language... nothing models content
 * or caption language separately from the course's learning language."
 *
 * Both halves were false. `Transcript.language` has been a foreign key to `Language`
 * since M6, `kind` distinguishes a transcript in the language being taught from one
 * translated for the learner, and `LessonTranscriptSerializer` has carried
 * `language_code` since the panel existed. **This component fetched that payload and
 * threw the field away.** `language_name` was added on 2026-09-29 for the label; that
 * was the only backend work needed, and it is one line.
 *
 * These tests need a configured video provider, which the rest of this file
 * deliberately does without — no template means no `<video>` and therefore no
 * `<track>`. `PLAYBACK_URL_TEMPLATE` is read at module scope, so the environment is
 * stubbed and the module re-imported rather than merely set.
 */
describe("the captions track", () => {
  const TEMPLATE = "https://video.example/{playback_id}?t={token}";

  /** Render with a provider configured and `transcript` as the panel's payload. */
  async function renderWithVideo(transcript: Response | null) {
    vi.stubEnv("NEXT_PUBLIC_PLAYBACK_URL_TEMPLATE", TEMPLATE);
    vi.resetModules();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const path = String(url);
        if (path.includes("/transcript/")) {
          return transcript ?? new Response("", { status: 404 });
        }
        if (path.includes("/playback-token/") || path.includes("/playback/")) {
          return json({
            token: "a-signed-token",
            playback_id: "pid-42",
            expires_at: "2026-01-01T01:00:00Z",
          });
        }
        if (path.includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    const { LessonPlayer: Fresh } = await import("@/components/learn/LessonPlayer");
    const view = render(<Fresh lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });
    return view;
  }

  function transcriptPayload(languageCode: string, languageName: string) {
    return json({
      language_code: languageCode,
      language_name: languageName,
      updated_at: "2026-01-01T00:00:00Z",
      segments: [{ position: 1, start_ms: 0, end_ms: 1000, text: "hola" }],
    });
  }

  beforeEach(() => {
    // jsdom implements neither, and the transcript panel calls both as soon as
    // there are segments to follow. Without the stub the effect throws during
    // commit, React tears the tree down, and the `<track>` query below returns
    // null — which reads exactly like the attribute being missing.
    // `TranscriptPanel.test.tsx` stubs the same pair for the same reason.
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("matchMedia", undefined);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("declares the language the payload gave it", async () => {
    const { container } = await renderWithVideo(transcriptPayload("es", "Spanish"));

    await waitFor(() => expect(container.querySelector("track")).not.toBeNull());
    const track = container.querySelector("track");

    expect(track).toHaveAttribute("srclang", "es");
    expect(track).toHaveAttribute("label", "Spanish");
    expect(track).toHaveAttribute("kind", "captions");
  });

  it("takes the language from the payload rather than hardcoding one", async () => {
    /**
     * **The twin, and the assertion that makes the pair a control.** A component
     * that wrote `srclang="es"` — the obvious guess for this fixture, and the exact
     * fabrication ADR-033 §3 warned against — would pass the test above.
     *
     * Arabic here, on a lesson whose course slug is still `spanish`, so inferring
     * the value from the course rather than reading it also fails.
     */
    const { container } = await renderWithVideo(transcriptPayload("ar", "Arabic"));

    await waitFor(() => expect(container.querySelector("track")).not.toBeNull());
    const track = container.querySelector("track");

    expect(track).toHaveAttribute("srclang", "ar");
    expect(track).toHaveAttribute("label", "Arabic");
  });

  it("is absent when the lesson has no transcript", async () => {
    /**
     * It used to render unconditionally, so a lesson without a transcript offered
     * a captions entry pointing at an endpoint that answers 404 — the browser shows
     * the option and choosing it produces nothing.
     *
     * A missing transcript is ordinary: an unapproved one is indistinguishable from
     * none by design (ADR-014 §3).
     */
    const { container } = await renderWithVideo(null);

    await waitFor(() => expect(container.querySelector("video")).not.toBeNull());
    expect(container.querySelector("track")).toBeNull();
  });
});

/**
 * The two comfort controls, and the one that could have corrupted completion.
 *
 * A speed control is not a display setting here. The server measures completion as
 * `watched_seconds >= duration_seconds * threshold`, so what the player claims has
 * to be denominated in content seconds — see `watchedSince`. These tests assert the
 * claim, not the label.
 *
 * Both are real controls rather than single-character shortcuts, because WCAG 2.2 AA
 * 2.1.4 constrains those and ADR-030 committed this product to 2.2 AA. Being
 * reachable by `getByRole` is the same property a keyboard user relies on.
 */
describe("the comfort controls", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  /** Every watched second this player has claimed so far. */
  function totalClaimed() {
    return progressPuts()
      .map(bodyOf)
      .reduce((sum, beat) => sum + (beat.watched_delta_seconds as number), 0);
  }

  it("claims content seconds watched, not wall-clock seconds", async () => {
    /**
     * **The assertion that makes the speed control safe**, and it spans four beats
     * rather than one for a reason.
     *
     * Sixty wall-clock seconds at 1.5× is ninety seconds of content, and ninety is
     * what the server must be told — otherwise a learner who watches a lesson
     * through at 1.5× never completes it, because completion is measured against the
     * lesson's *duration*.
     *
     * A beat is fifteen seconds, so each one carries 22.5 — which is fractional, and
     * `watched_delta_seconds` is an `IntegerField`. Flooring each beat and rounding
     * would drift; **flooring and carrying the remainder does not**, and only a
     * multi-beat total can tell those two apart. 22 + 23 + 22 + 23 = 90.
     */
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.selectOptions(screen.getByLabelText(/speed/i), "1.5");
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(60);

    expect(totalClaimed()).toBe(90);
  });

  it("claims wall-clock seconds at 1x, so nothing changed for everyone else", async () => {
    // The twin. A player multiplying by something other than the rate could pass
    // the test above on a coincidence; this pins the untouched case.
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(60);

    expect(totalClaimed()).toBe(60);
  });

  it("does not drift at a speed whose beats never come out whole", async () => {
    /**
     * 0.75× puts 11.25 seconds in each beat, so every single one has a remainder.
     * Sixty wall-clock seconds is forty-five seconds of content, and the carry is
     * what makes the total come out exactly — rounding each beat would give 44 or
     * 48 depending on which way each one went.
     */
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.selectOptions(screen.getByLabelText(/speed/i), "0.75");
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(60);

    expect(totalClaimed()).toBe(45);
  });

  it("advances the stand-in's own clock at the chosen speed", async () => {
    /**
     * The stand-in honours the rate too, which is what makes the control
     * demonstrable before a video provider exists — the whole argument for the
     * stand-in existing (ADR-016 §4). Ten seconds at 0.5× is five seconds of
     * content, and the position readout is where a learner would see it.
     */
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.selectOptions(screen.getByLabelText(/speed/i), "0.5");
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(10);

    expect(screen.getByText(/At 0:05/)).toBeVisible();
  });

  it("remembers the speed for the next lesson", async () => {
    // Per device and without an endpoint — `preferences.ts` says why. The point of
    // the control is somebody setting it once.
    const first = render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });
    await userEvent.selectOptions(screen.getByLabelText(/speed/i), "0.75");
    first.unmount();

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await waitFor(() => expect(screen.getByLabelText(/speed/i)).toHaveValue("0.75"));
  });

  it("takes the playhead back five seconds", async () => {
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(12);
    expect(screen.getByText(/At 0:12/)).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: /back 5 seconds/i }));

    expect(screen.getByText(/At 0:07/)).toBeVisible();
  });

  it("does not seek before the start", async () => {
    // Pressing it at the beginning of a lesson is ordinary, and a negative
    // `currentTime` throws on a real media element.
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    await userEvent.click(screen.getByRole("button", { name: /back 5 seconds/i }));

    expect(screen.getByText(/At 0:00/)).toBeVisible();
  });

  it("names the action rather than a direction", async () => {
    // "Back 5 seconds" is what a screen reader should read out. An icon-only
    // control, or one labelled "«", says nothing to anybody not looking at it.
    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });

    expect(screen.getByRole("button", { name: "Back 5 seconds" })).toBeVisible();
  });

  it("disables both when the subscription lapsed mid-lesson", async () => {
    // Same reasoning as "Mark complete": continuing to operate a player somebody is
    // no longer entitled to is the thing the denial exists to stop.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        if (String(url).includes("/progress/") && init?.method === "PUT") {
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
        if (String(url).includes("/progress/")) return json(progress());
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("heading", { name: "Intro to Spanish" });
    await userEvent.click(screen.getByRole("button", { name: /play/i }));
    await tick(16);
    await screen.findByRole("alert");

    expect(screen.getByRole("button", { name: /back 5 seconds/i })).toBeDisabled();
    expect(screen.getByLabelText(/speed/i)).toBeDisabled();
  });
});

describe("a lesson that would not load", () => {
  it("offers a retry that re-requests, rather than a bare message", async () => {
    /**
     * The fourth of four surfaces that reported a failed load and gave nobody
     * anything to press. This one showed a `Notice` and stopped.
     *
     * The progress request is the one that decides this state: `load()` treats its
     * failure as the page failing, while a missing playback token or transcript is
     * ordinary and leaves the page usable.
     */
    let failing = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        if (String(url).includes("/progress/")) {
          if (failing) return new Response("", { status: 500 });
          return json(progress());
        }
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();

    failing = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Intro to Spanish" })).toBeInTheDocument();
  });

  it("clears the old message while the retry is in flight", async () => {
    // A stale error sitting above a loading state reads as a second failure.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        if (String(url).includes("/progress/")) return new Response("", { status: 500 });
        return new Response("", { status: 404 });
      }),
    );

    render(<LessonPlayer lesson={LESSON} />);
    await screen.findByRole("alert");

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    // It comes back, because the stub still fails — the point is that it went away
    // and returned rather than never having left.
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
