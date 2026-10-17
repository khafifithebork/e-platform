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
import { axeViolations } from "@/test/axe";

function segment(position: number, start_ms: number, end_ms: number, text: string) {
  return { position, start_ms, end_ms, text } as unknown as TranscriptSegment;
}

const SEGMENTS: TranscriptSegment[] = [
  segment(1, 0, 2000, "Hola, buenos días."),
  segment(2, 2000, 5000, "¿Cómo estás?"),
  segment(3, 7000, 9000, "Muy bien, gracias."),
];

let cueTop = 250;
let cueHeight = 44;

beforeEach(() => {
  // Geometry is explicit: jsdom does not lay out the scrolling list.
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.scrollTo = vi.fn();
  cueTop = 250; cueHeight = 44;
  vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(100);
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return this.tagName === "OL" ? new DOMRect(0, 100, 200, 100) : new DOMRect(0, cueTop, 200, cueHeight);
  });
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
  it("preserves transcript language, current cue and seeking with long text", async () => {
    const onSeek = vi.fn();
    const text = "مرحبا".repeat(100);
    render(<TranscriptPanel segments={[segment(1, 0, 2000, text)]} positionSeconds={1} onSeek={onSeek} languageCode="ar" />);
    expect(screen.getByRole("list")).toHaveAttribute("lang", "ar");
    const cue = screen.getByRole("button", { name: text });
    expect(cue).toHaveAttribute("aria-current", "true");
    await userEvent.tab();
    expect(cue).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onSeek).toHaveBeenCalledWith(0);
  });

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
  it("follows cues without scrolling ancestors", () => {
    const { container } = render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ top: 94, behavior: "instant" });
    expect(vi.mocked(Element.prototype.scrollTo).mock.instances[0]).toBe(container.querySelector("ol"));
  });

  it("scrolls no further than it must", () => {
    cueTop = 180;
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ top: 24, behavior: "instant" });
  });

  it("leaves visible cues still", () => {
    cueTop = 120;
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("keeps keyboard-focused cues visible and resumes following after focus leaves", () => {
    const { rerender } = render(<TranscriptPanel segments={SEGMENTS} positionSeconds={6} onSeek={vi.fn()} />);
    const focused = screen.getByRole("button", { name: "Hola, buenos días." });
    focused.focus();
    rerender(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(focused).toHaveFocus();
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
    focused.blur();
    rerender(<TranscriptPanel segments={SEGMENTS} positionSeconds={7} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledOnce();
  });

  it("follows a cue above the list using its existing scroll offset", () => {
    cueTop = 70;
    const { container, rerender } = render(<TranscriptPanel segments={SEGMENTS} positionSeconds={6} onSeek={vi.fn()} />);
    container.querySelector("ol")!.scrollTop = 80;
    rerender(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ top: 50, behavior: "instant" });
  });

  it("handles oversized cues without oscillation", () => {
    cueTop = 70; cueHeight = 200;
    const { rerender } = render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
    cueTop = 250;
    rerender(<TranscriptPanel segments={SEGMENTS} positionSeconds={7} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ top: 150, behavior: "instant" });
  });

  it("does not scroll during a gap", () => {
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={6} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("does not scroll again while the same line is current", () => {
    const { rerender } = render(<TranscriptPanel segments={SEGMENTS} positionSeconds={2.1} onSeek={vi.fn()} />);
    rerender(<TranscriptPanel segments={SEGMENTS} positionSeconds={2.9} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledTimes(1);
  });

  // The approved correction replaces repeated smooth movement with immediate
  // panel-only following for both preferences; existing seeking tests stay intact.
  it.each([false, true])("follows immediately with reduced motion set to %s", (matches) => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches })));
    render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "instant" }));
  });

  it("survives an environment with no matchMedia", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(() => render(<TranscriptPanel segments={SEGMENTS} positionSeconds={3} onSeek={vi.fn()} />)).not.toThrow();
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

describe("what language the cues are in", () => {
  /**
   * **WCAG 3.1.2 Language of Parts, and the fault that prompted the component change.**
   *
   * Every one of the fixtures above is Spanish, inside a document whose `<html lang>`
   * is English, and until 2026-10-03 the panel said nothing about that. Twenty-six
   * tests passed over the top of it, including an axe run — axe cannot flag it,
   * because no attribute is *wrong*, one is merely absent, and the tool has no way to
   * know "Hola, buenos días" is not English.
   */
  it("marks the list with the language the payload says", () => {
    const { container } = render(
      <TranscriptPanel
        segments={SEGMENTS}
        positionSeconds={0}
        onSeek={vi.fn()}
        languageCode="es"
      />,
    );

    expect(container.querySelector("ol")).toHaveAttribute("lang", "es");
  });

  it("omits lang entirely when the language is unknown", () => {
    /**
     * The twin, and the more important half.
     *
     * The alternative was defaulting to `"en"`, which would have passed a test
     * asserting the attribute exists while telling a screen reader to pronounce
     * Spanish as English — confidently. An absent `lang` inherits the document's and
     * is at least honest about having no information; a wrong one is a claim.
     *
     * This is also the real case rather than a hypothetical: the field arrived with
     * the transcript endpoint, and a lesson whose transcript has not been through
     * Deepgram yet has no `language_code` to pass.
     */
    const { container } = render(
      <TranscriptPanel segments={SEGMENTS} positionSeconds={0} onSeek={vi.fn()} />,
    );

    const list = container.querySelector("ol");

    expect(list).not.toBeNull();
    expect(list?.hasAttribute("lang")).toBe(false);
  });

  it("marks the list once rather than every line", () => {
    // Not a style preference: 200 identical attributes is what the obvious
    // implementation produces, and it makes the panel's language a property of each
    // line rather than of the transcript. Pinned so a later refactor has to think
    // about it.
    const { container } = render(
      <TranscriptPanel
        segments={SEGMENTS}
        positionSeconds={0}
        onSeek={vi.fn()}
        languageCode="es"
      />,
    );

    expect(container.querySelectorAll("[lang]")).toHaveLength(1);
  });

  it("has no axe violations with a language set", async () => {
    const { container } = render(
      <TranscriptPanel
        segments={SEGMENTS}
        positionSeconds={1}
        onSeek={vi.fn()}
        languageCode="es"
      />,
    );

    expect(await axeViolations(container)).toEqual([]);
  });
});
