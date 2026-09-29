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
 *
 * ## Why `rate` exists, and why it is not cosmetic
 *
 * **The server compares the accumulated total against the lesson's *duration***:
 * `is_complete` is `watched_seconds >= duration_seconds * LESSON_COMPLETION_THRESHOLD`.
 * So `watched_seconds` has to be denominated in *content* seconds, the same units
 * as a duration — not in wall-clock seconds.
 *
 * At 1× the two are identical, which is why this went unnoticed until a speed
 * control existed. Once one does, wall-clock counting breaks completion in both
 * directions:
 *
 * - **At 1.5×** a learner consumes a ten-minute lesson in under seven wall-clock
 *   minutes, claims under seven minutes of watching, and **never completes it**
 *   however many times they watch it through.
 * - **At 0.5×** ten wall-clock minutes cover five minutes of content, so the lesson
 *   **completes having been half heard** — which is exactly the "scrubbed to the end
 *   and heard nothing" failure ADR-016 §2 built this rule to prevent.
 *
 * Scaling here rather than on the server is deliberate: the server cannot know the
 * rate, and sending it would be a second number to validate and to disbelieve. What
 * arrives is what it already expects — content seconds watched.
 *
 * The clamp applies *after* scaling, so what is claimed is bounded by what the
 * server will accept rather than by what the wall clock did.
 */
export function watchedSince(
  elapsedSeconds: number,
  playing: boolean,
  rate = 1,
): number {
  if (!playing || !Number.isFinite(elapsedSeconds) || elapsedSeconds <= 0) return 0;
  // A rate that is not a usable multiplier counts as 1 rather than as zero
  // watching: losing somebody's progress is the worse failure, and `preferences.ts`
  // already refuses to store anything outside the offered set.
  const multiplier = Number.isFinite(rate) && rate > 0 ? rate : 1;

  return Math.min(elapsedSeconds * multiplier, MAX_DELTA_SECONDS);
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
