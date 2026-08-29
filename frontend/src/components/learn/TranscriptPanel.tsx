"use client";

import { useEffect, useRef } from "react";

import type { TranscriptSegment } from "@/lib/api/client";

interface TranscriptPanelProps {
  segments: TranscriptSegment[];
  /** Playhead, in seconds, so the current line can be marked. */
  positionSeconds: number;
  onSeek: (seconds: number) => void;
}

/** The cue covering this moment, or -1. */
export function currentSegmentIndex(
  segments: TranscriptSegment[],
  positionSeconds: number,
): number {
  const ms = positionSeconds * 1000;
  return segments.findIndex((segment) => ms >= segment.start_ms && ms < segment.end_ms);
}

/**
 * A transcript you can read along with, and click to seek.
 *
 * Rendered as text, never as markup. Segment text comes from a transcription
 * provider and then from an instructor's edits, which makes it user-supplied
 * content twice over — `dangerouslySetInnerHTML` on it would be an XSS hole
 * with a review workflow attached (CLAUDE.md §6).
 *
 * Buttons rather than clickable list items: seeking is an action, and a
 * keyboard user needs to reach it. That is also why the current line is marked
 * with `aria-current` and not only a background colour.
 *
 * **The current line is scrolled into view, which is what makes it a transcript
 * you can follow rather than one you can search.** Marking line 87 of 200 is
 * worth nothing if line 87 is off-screen — added at M16 T7, when this component
 * was first exercised.
 */
export function TranscriptPanel({ segments, positionSeconds, onSeek }: TranscriptPanelProps) {
  const current = currentSegmentIndex(segments, positionSeconds);
  const currentRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (current < 0) return;

    /**
     * `block: "nearest"` rather than `"center"`, and the difference is the
     * whole reason this is bearable.
     *
     * "nearest" does nothing when the line is already visible, so a learner
     * who scrolled up to re-read a sentence is only pulled back when the
     * playhead leaves the part of the transcript they are looking at — rather
     * than every few seconds. Following a transcript is a trade-off between
     * keeping up and staying put, and this is the cheapest version that does
     * not fight the reader.
     */
    currentRef.current?.scrollIntoView({
      block: "nearest",
      // A transcript advancing every few seconds is exactly the repeated
      // motion `prefers-reduced-motion` exists for, and smooth scrolling it
      // can trigger nausea rather than merely annoy.
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
    // Deliberately only on the index. Running on every position change would
    // call this once a second while nothing moved.
  }, [current]);

  return (
    <section aria-label="Transcript" className="flex h-full flex-col">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-ink-subtle">
        Transcript
      </h2>

      <ol className="flex-1 space-y-1 overflow-y-auto pr-1">
        {segments.map((segment, index) => (
          <li key={segment.position}>
            <button
              ref={index === current ? currentRef : undefined}
              type="button"
              onClick={() => onSeek(segment.start_ms / 1000)}
              aria-current={index === current ? "true" : undefined}
              className={`w-full rounded-[--radius-sm] px-3 py-2 text-left text-sm leading-relaxed
                transition-colors hover:bg-surface-sunken
                ${
                  index === current
                    ? "bg-accent-subtle font-medium text-ink"
                    : "text-ink-muted"
                }`}
            >
              {segment.text}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * Whether the visitor asked for less motion.
 *
 * Read at call time rather than cached: somebody can change the setting while
 * a lesson is open, and a value captured on mount would keep animating for the
 * rest of the session. `matchMedia` is guarded because jsdom does not
 * implement it, and a test environment is not a reason to crash a player.
 */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
