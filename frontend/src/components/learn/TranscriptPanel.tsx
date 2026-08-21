"use client";

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
 */
export function TranscriptPanel({ segments, positionSeconds, onSeek }: TranscriptPanelProps) {
  const current = currentSegmentIndex(segments, positionSeconds);

  return (
    <section aria-label="Transcript" className="flex h-full flex-col">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-ink-subtle">
        Transcript
      </h2>

      <ol className="flex-1 space-y-1 overflow-y-auto pr-1">
        {segments.map((segment, index) => (
          <li key={segment.position}>
            <button
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
