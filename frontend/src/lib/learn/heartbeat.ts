/**
 * The watch loop, as arithmetic.
 *
 * Kept out of the component because the interesting part is not React: it is
 * deciding *how much of the elapsed wall-clock time counts as watching*, and
 * that is the number the server folds into `watched_seconds` — the number
 * completion is measured against (ADR-016 §2).
 *
 * The rule is: only time when the media was actually playing counts. A learner
 * who opens a lesson, pauses, and goes to lunch has watched nothing, and a
 * player that reported wall-clock time would complete the lesson for them.
 */

/** How often a playing lesson reports in. */
export const BEAT_SECONDS = 15;

/**
 * The server clamps a delta at `PROGRESS_MAX_HEARTBEAT_SECONDS` and its
 * serializer rejects anything past an hour. Clamping here too means a browser
 * that was suspended for a day sends a plausible number rather than having a
 * wild one quietly trimmed — the two agreeing is what keeps the client's own
 * display honest.
 */
export const MAX_DELTA_SECONDS = 60;

export interface Beat {
  positionSeconds: number;
  watchedDeltaSeconds: number;
}

/**
 * How much watching happened between two samples.
 *
 * Takes elapsed wall-clock seconds and returns what may be claimed. Negative
 * elapsed time — a clock adjustment, or a `performance.now` reading that went
 * backwards — is zero, never a rewind of somebody's progress.
 */
export function watchedSince(elapsedSeconds: number, playing: boolean): number {
  if (!playing || !Number.isFinite(elapsedSeconds) || elapsedSeconds <= 0) return 0;
  return Math.min(elapsedSeconds, MAX_DELTA_SECONDS);
}

/**
 * Whether a beat is worth sending.
 *
 * A paused player at the same position has nothing to say, and saying it
 * anyway is a write every fifteen seconds per open tab for no information.
 * A moved playhead does count even with no watched time, because "resume"
 * should follow a learner who scrubbed and then stopped.
 */
export function worthSending(beat: Beat, lastSentPosition: number | null): boolean {
  // Nothing watched and nowhere reached is not a report, it is noise — and it
  // is the specific beat that overwrites somebody's resume point with zero.
  if (beat.watchedDeltaSeconds <= 0 && beat.positionSeconds <= 0) return false;

  if (beat.watchedDeltaSeconds > 0) return true;
  return lastSentPosition === null || Math.round(beat.positionSeconds) !== lastSentPosition;
}
