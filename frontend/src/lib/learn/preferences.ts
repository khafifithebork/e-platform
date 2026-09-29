/**
 * Preferences a learner sets once and expects to hold.
 *
 * **The first use of `localStorage` in this application's production code**, so
 * the reasoning is here rather than at the call site.
 *
 * Invariant 9 forbids anything *auth-related* in storage, and a playback speed is
 * not that — the same line ADR-032 §3 drew for a theme. What is stored is a number
 * between 0.5 and 1.5 that reveals nothing about anybody and grants nothing to
 * whoever reads it.
 *
 * **Per device, deliberately.** There is no user-preferences endpoint, and adding
 * one for this would be a schema, a migration and a write path for a number that
 * differs per device anyway: a learner on a phone in a noisy place and at a desk
 * with headphones does not want one answer for both.
 *
 * **Every access is guarded.** `localStorage` throws rather than returning null in
 * a private window with site data blocked, and it comes back empty in previews.
 * A player that crashed because a browser declined to remember a speed would be a
 * worse bug than the one this fixes.
 */

const RATE_KEY = "lingua.playbackRate";

/**
 * The speeds offered, slowest first.
 *
 * **Weighted towards slow, and that is the product decision.** A lecture player
 * offers 2× because the value is getting through material faster; here the value is
 * hearing a phrase you cannot yet parse, and 0.5× is the setting that does that.
 * Above 1.5× native speech in a language you are learning stops being intelligible,
 * so the faster end is short rather than absent.
 */
export const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5] as const;

export type PlaybackRate = (typeof PLAYBACK_RATES)[number];

export const DEFAULT_PLAYBACK_RATE: PlaybackRate = 1;

/** Whether `value` is one of the offered speeds. */
function isOffered(value: number): value is PlaybackRate {
  return (PLAYBACK_RATES as readonly number[]).includes(value);
}

/**
 * The stored speed, or the default.
 *
 * **Validated against the offered set rather than merely parsed**, because this
 * value is assigned to `HTMLMediaElement.playbackRate`. A hand-edited or corrupted
 * entry of `"1e999"`, `"-1"` or `"abc"` would otherwise reach that property as
 * `Infinity`, a negative, or `NaN` — the first two throw, and the third silently
 * stops playback. Storage is not input we control, and treating it as such is how a
 * preference becomes a crash.
 */
export function readPlaybackRate(): PlaybackRate {
  try {
    const stored = window.localStorage.getItem(RATE_KEY);
    if (stored === null) return DEFAULT_PLAYBACK_RATE;

    const parsed = Number(stored);
    return isOffered(parsed) ? parsed : DEFAULT_PLAYBACK_RATE;
  } catch {
    // Blocked, unavailable, or a preview. Not an error worth surfacing: the
    // learner gets the default speed and the lesson plays.
    return DEFAULT_PLAYBACK_RATE;
  }
}

/** Remember the speed, if this browser will. */
export function writePlaybackRate(rate: PlaybackRate): void {
  try {
    window.localStorage.setItem(RATE_KEY, String(rate));
  } catch {
    // Quota, private mode, or blocked site data. The speed still applies to this
    // session; only remembering it fails, and telling somebody that would be a
    // message about a request they did not make.
  }
}

/**
 * How far back the replay control goes.
 *
 * Five seconds rather than ten: the action is "say that again", and a phrase in a
 * language you are learning is a few seconds long. Ten overshoots into the previous
 * sentence, which means listening to something you already understood before
 * reaching the part you did not.
 */
export const REPLAY_SECONDS = 5;

/** Where a replay lands, never before the start. */
export function replayFrom(positionSeconds: number): number {
  return Math.max(0, positionSeconds - REPLAY_SECONDS);
}
