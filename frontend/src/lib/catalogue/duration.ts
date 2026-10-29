/**
 * Rendering a course's total length.
 *
 * The API gives seconds and gives `null` when the total is not yet knowable —
 * ADR-041: a course with one unmeasured lesson withholds its whole total
 * rather than publish the other lessons' minutes as the answer. So the only
 * honest thing to render for `null` is nothing, and that decision lives here
 * rather than in the page: a page asking `?? 0` would turn "unknown" into
 * "zero minutes" in one keystroke.
 *
 * English only, deliberately. ADR-033 §1 records the interface language as
 * English and its §4 defers localisation until a launch locale is named. When
 * that happens this is one of the strings that moves, which is easier to find
 * as a named function than as JSX.
 */

const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;

/**
 * `null` when there is nothing honest to say, otherwise a short human length.
 *
 * Rounds to the nearest minute, and never down to "0 minutes": a course that
 * exists is at least a minute's worth from a learner's point of view, and
 * "0 minutes" reads as an error rather than as a very short course.
 */
export function formatCourseDuration(totalSeconds: number | null | undefined): string | null {
  if (totalSeconds === null || totalSeconds === undefined) return null;
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return null;

  const totalMinutes = Math.max(1, Math.round(totalSeconds / SECONDS_PER_MINUTE));
  const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);
  const minutes = totalMinutes % MINUTES_PER_HOUR;

  if (hours === 0) return `${minutes} min`;
  if (minutes === 0) return `${hours} hr`;
  return `${hours} hr ${minutes} min`;
}
