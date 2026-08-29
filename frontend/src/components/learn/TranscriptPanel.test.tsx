/**
 * The transcript, tested for the first time.
 *
 * Written at M7 alongside the player and never executed. The interesting part
 * is not that it renders lines — it is the boundary arithmetic in
 * `currentSegmentIndex`, which decides which line is "now", and which is
 * off-by-one in both directions if it is written the obvious way.
 *
 * **The text is user-supplied twice over**: a transcription provider writes it
 * and an instructor edits it. CLAUDE.md §6 forbids `dangerouslySetInnerHTML`
 * on user content, and a transcript is the most tempting place in this
 * application to reach for it — highlighting a searched term is the obvious
 * feature that would want raw HTML.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TranscriptPanel, currentSegmentIndex } from "@/components/learn/TranscriptPanel";
import type { TranscriptSegment } from "@/lib/api/client";

function segment(position: number, start_ms: number, end_ms: number, text: string) {
  return { position, start_ms, end_ms, text } as unknown as TranscriptSegment;
}

const SEGMENTS: TranscriptSegment[] = [
  segment(1, 0, 2000, "Hola, buenos días."),
  segment(2, 2000, 5000, "¿Cómo estás?"),
  segment(3, 7000, 9000, "Muy bien, gracias."),
];

beforeEach(() => {
  // jsdom implements neither, and both are called on every index change.
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal("matchMedia", undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("currentSegmentIndex", () => {
  it("finds the cue covering the moment", () => {
    expect(currentSegmentIndex(SEGMENTS, 3)).toBe(1);
  });

  it("includes the first instant of a cue", () => {
    // `>=` on the start. Exclusive here would leave a one-frame gap at every
    // boundary where nothing is highlighted.
    expect(currentSegmentIndex(SEGMENTS, 2)).toBe(1);
  });

  it("excludes the last instant of a cue", () => {
    /**
     * `<` on the end, so a moment belongs to exactly one cue.
     *
     * Segment one runs 0–2000ms and segment two starts at 2000ms. Inclusive on
     * both sides, 2.0s would match both — and `findIndex` returns the first,
     * so the highlight would sit on the line that just finished for as long as
     * the boundary lasted.
     *
     * Asserted as "the answer is the later cue, not the earlier one", which is
     * what exclusivity actually buys. An earlier version asserted a number at
     * 5s, which lands in a gap and proves nothing about boundaries.
     */
    expect(currentSegmentIndex(SEGMENTS, 2)).not.toBe(0);
    expect(currentSegmentIndex(SEGMENTS, 2)).toBe(1);
  });

  it("returns -1 in a gap between cues", () => {
    // Real transcripts have silence. 5s–7s belongs to nothing, and inventing
    // a nearest match would highlight a line nobody is speaking.
    expect(currentSegmentIndex(SEGMENTS, 6)).toBe(-1);
  });

  it("returns -1 before the first cue and after the last", () => {
    expect(currentSegmentIndex(SEGMENTS, 100)).toBe(-1);
  });

  it("returns -1 for an empty transcript", () => {
    expect(currentSegmentIndex([], 3)).toBe(-1);
  });
});

describe("the panel", () => {
  it("renders every line", () => {
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={0} onSeek={vi.fn()} />);

    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("names itself, so it can be found as a landmark", () => {
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={0} onSeek={vi.fn()} />);

    expect(screen.getByRole("region", { name: "Transcript" })).toBeInTheDocument();
  });

  it("marks the current line for assistive technology", () => {
    // Not only a background colour. `aria-current` is what a screen reader
    // announces, and colour alone is invisible to it and to anyone who cannot
    // distinguish this one.
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);

    expect(screen.getByRole("button", { name: "¿Cómo estás?" })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("marks exactly one line", () => {
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);

    const marked = screen
      .getAllByRole("button")
      .filter((button) => button.getAttribute("aria-current") === "true");

    expect(marked).toHaveLength(1);
  });

  it("marks none during a gap", () => {
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={6} onSeek={vi.fn()} />);

    const marked = screen
      .getAllByRole("button")
      .filter((button) => button.getAttribute("aria-current") === "true");

    expect(marked).toHaveLength(0);
  });
});

describe("seeking", () => {
  it("jumps to the start of a clicked line, in seconds", async () => {
    // The API stores milliseconds and the player takes seconds. Handing over
    // milliseconds would seek to 7000 seconds — just under two hours into a
    // ten-minute lesson.
    const onSeek = vi.fn();
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={0} onSeek={onSeek} />);

    await userEvent.click(screen.getByRole("button", { name: "Muy bien, gracias." }));

    expect(onSeek).toHaveBeenCalledWith(7);
  });

  it("is reachable by keyboard", async () => {
    // Buttons rather than clickable list items, which is the whole reason the
    // markup is shaped this way.
    const onSeek = vi.fn();
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={0} onSeek={onSeek} />);

    await userEvent.tab();
    await userEvent.keyboard("{Enter}");

    expect(onSeek).toHaveBeenCalledWith(0);
  });
});

describe("following along", () => {
  it("scrolls the current line into view", () => {
    // Marking line 87 of 200 is worth nothing if line 87 is off-screen. This
    // is what makes it a transcript you can follow rather than one you can
    // search — added at T7.
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("scrolls no further than it must", () => {
    // `block: "nearest"` does nothing when the line is already visible, so a
    // learner who scrolled up to re-read is only pulled back when the playhead
    // leaves what they are looking at — rather than every few seconds.
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: "nearest" }),
    );
  });

  it("does not scroll during a gap", () => {
    // Nothing is current, so there is nothing to follow. Scrolling anyway
    // would jump to whichever line happened to hold the ref last.
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={6} onSeek={vi.fn()} />);

    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("does not scroll again while the same line is current", () => {
    // The effect depends on the index, not the position. Running on every
    // position change would call this once a second while nothing moved.
    const { rerender } = render(
      <TranscriptPanel segments={SEGMENTS} positionSeconds={2.1} onSeek={vi.fn()} />,
    );
    rerender(<TranscriptPanel segments={SEGMENTS} positionSeconds={2.9} onSeek={vi.fn()} />);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("animates by default", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));

    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" }),
    );
  });

  it("does not animate when the visitor asked for less motion", () => {
    // A transcript advancing every few seconds is exactly the repeated motion
    // this setting exists for, and smooth scrolling it can cause nausea rather
    // than merely annoy.
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));

    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "auto" }),
    );
  });

  it("survives an environment with no matchMedia", () => {
    // jsdom has none, and neither does a server render. Reading it
    // unguardedly would crash the player in both.
    vi.stubGlobal("matchMedia", undefined);

    expect(() =>
      render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />),
    ).not.toThrow();
  });
});

describe("the transcript is text, never markup", () => {
  it("renders a script tag as characters", () => {
    // Written by a transcription provider, then edited by an instructor — user
    // content twice over, and §6 forbids `dangerouslySetInnerHTML` on it.
    const hostile = [segment(1, 0, 2000, '<img src=x onerror="alert(1)">')];

    render(<TranscriptPanel segments={hostile} positionSeconds={0} onSeek={vi.fn()} />);

    expect(screen.getByRole("button", { name: /<img src=x/ })).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("uses no dangerouslySetInnerHTML", async () => {
    // Structural, and aimed at a specific future change: highlighting a
    // searched term inside a line is the obvious reason somebody would reach
    // for raw HTML here.
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");

    // Comments stripped first. The component's own docstring explains why
    // `dangerouslySetInnerHTML` is forbidden here, so grepping the raw file
    // fails against correct code — the identical mistake M15 made with its
    // price guard, and the reason that one strips comments too.
    const source = readFileSync(
      join(process.cwd(), "src", "components", "learn", "TranscriptPanel.tsx"),
      "utf8",
    )
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");

    expect(source).not.toContain("dangerouslySetInnerHTML");
  });
});
