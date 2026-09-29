/**
 * The playback-speed preference, and the replay offset.
 *
 * Two properties carry the weight here, and neither is about remembering a number:
 *
 * 1. **A stored value is not trusted.** It is assigned to
 *    `HTMLMediaElement.playbackRate`, where `Infinity` and a negative both throw and
 *    `NaN` silently stops playback. Storage is not input we control.
 * 2. **Storage failing is not an error.** `localStorage` throws rather than
 *    returning null in a private window with site data blocked. A player that
 *    crashed because a browser declined to remember a speed would be worse than the
 *    inconvenience it was trying to avoid.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_PLAYBACK_RATE,
  PLAYBACK_RATES,
  REPLAY_SECONDS,
  readPlaybackRate,
  replayFrom,
  writePlaybackRate,
} from "@/lib/learn/preferences";

const KEY = "lingua.playbackRate";

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("remembering a speed", () => {
  it("returns the default when nothing is stored", () => {
    expect(readPlaybackRate()).toBe(DEFAULT_PLAYBACK_RATE);
  });

  it("round-trips every offered speed", () => {
    // Every one, not a sample: the parse is `Number(...)` and a set containing
    // both integers and decimals is where a stringify/parse pair goes wrong.
    for (const rate of PLAYBACK_RATES) {
      writePlaybackRate(rate);
      expect(readPlaybackRate(), String(rate)).toBe(rate);
    }
  });

  it("stores it under a namespaced key", () => {
    // Artifacts and previews share an origin per deployment, and an unprefixed
    // "playbackRate" is the kind of key two applications collide on.
    writePlaybackRate(1.5);

    expect(window.localStorage.getItem(KEY)).toBe("1.5");
  });
});

describe("a value that is not one of ours", () => {
  /**
   * **The property this module exists for.** Each of these reaches
   * `video.playbackRate` if it is merely parsed rather than validated: `Infinity`
   * and `-1` throw, `NaN` stops playback silently, and `3` is a speed nothing in the
   * interface can get you back from because it is not in the menu.
   */
  it.each([
    ["not a number", "abc"],
    ["empty", ""],
    ["infinite", "1e999"],
    ["negative", "-1"],
    ["zero", "0"],
    ["off the menu", "3"],
    ["nearly right", "1.1"],
    ["an object", "{}"],
  ])("falls back to the default for %s", (_label, stored) => {
    window.localStorage.setItem(KEY, stored);

    expect(readPlaybackRate()).toBe(DEFAULT_PLAYBACK_RATE);
  });
});

describe("when the browser refuses storage", () => {
  it("reads the default rather than throwing", () => {
    // What a private window with site data blocked does: it throws on access,
    // rather than returning null.
    vi.spyOn(window.localStorage.__proto__, "getItem").mockImplementation(() => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    });

    expect(() => readPlaybackRate()).not.toThrow();
    expect(readPlaybackRate()).toBe(DEFAULT_PLAYBACK_RATE);
  });

  it("writes without throwing, and the session still works", () => {
    vi.spyOn(window.localStorage.__proto__, "setItem").mockImplementation(() => {
      throw new DOMException("Quota exceeded.", "QuotaExceededError");
    });

    expect(() => writePlaybackRate(0.5)).not.toThrow();
  });
});

describe("the replay offset", () => {
  it("goes back five seconds", () => {
    expect(replayFrom(30)).toBe(30 - REPLAY_SECONDS);
  });

  it("never goes before the start", () => {
    // Pressing it twice at the beginning of a lesson is the ordinary case, and a
    // negative `currentTime` throws on a real media element.
    expect(replayFrom(2)).toBe(0);
    expect(replayFrom(0)).toBe(0);
  });

  it("is five rather than ten, and the constant is the one used", () => {
    /**
     * Pinned because it is a product decision, not an implementation detail: the
     * action is "say that again", and a phrase in a language you are learning is a
     * few seconds long. Ten overshoots into the previous sentence.
     */
    expect(REPLAY_SECONDS).toBe(5);
  });
});
