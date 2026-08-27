/**
 * The watch loop's arithmetic.
 *
 * This module was written at M7 with no way to run a test against it, which is
 * why it is the first thing tested now: it decides how much of a learner's
 * elapsed time counts as watching, and that number is what completion is
 * measured against (ADR-016 §2). Getting it wrong either completes a lesson
 * nobody watched or refuses to complete one somebody did.
 *
 * Every case here is a property the source file states in prose. Testing what
 * a comment claims is the point — the claims were unverifiable until now.
 */

import { describe, expect, it } from "vitest";

import { MAX_DELTA_SECONDS, watchedSince, worthSending } from "@/lib/learn/heartbeat";

describe("watchedSince", () => {
  it("counts elapsed time while playing", () => {
    expect(watchedSince(10, true)).toBe(10);
  });

  it("counts nothing while paused", () => {
    // "A learner who opens a lesson, pauses, and goes to lunch has watched
    // nothing, and a player that reported wall-clock time would complete the
    // lesson for them."
    expect(watchedSince(3600, false)).toBe(0);
  });

  it("clamps a suspended browser to the server's own ceiling", () => {
    // A laptop closed overnight wakes with an enormous delta. Clamping here as
    // well as server-side is what keeps the client's displayed progress equal
    // to what was actually recorded.
    expect(watchedSince(86_400, true)).toBe(MAX_DELTA_SECONDS);
  });

  it("treats a backwards clock as zero, never as a rewind", () => {
    // Negative elapsed time is a clock adjustment, not a correction to
    // somebody's progress. Returning the negative would subtract from
    // watched_seconds and un-complete a finished lesson.
    expect(watchedSince(-30, true)).toBe(0);
  });

  it("treats a non-finite reading as nothing watched", () => {
    // `performance.now()` differences can be NaN across some suspend paths,
    // and NaN would reach the server as a rejected payload at best.
    //
    // Infinity returns 0 rather than the clamp, and that is the right answer
    // even though clamping looks like the obvious one: an infinite reading is
    // not a very long watch, it is a broken clock, and crediting a full minute
    // of watching to a broken clock is how a lesson completes itself. Asserted
    // here because the first version of this test expected the clamp and was
    // wrong — the code was right.
    expect(watchedSince(Number.NaN, true)).toBe(0);
    expect(watchedSince(Number.POSITIVE_INFINITY, true)).toBe(0);
  });
});

describe("worthSending", () => {
  it("sends a beat that watched something", () => {
    expect(worthSending({ positionSeconds: 30, watchedDeltaSeconds: 15 }, null)).toBe(true);
  });

  it("stays silent when nothing was watched and nowhere was reached", () => {
    // "It is the specific beat that overwrites somebody's resume point with
    // zero." A paused player at position 0 has nothing to report, and
    // reporting it is a write every fifteen seconds per open tab.
    expect(worthSending({ positionSeconds: 0, watchedDeltaSeconds: 0 }, null)).toBe(false);
  });

  it("sends a scrub that watched nothing", () => {
    // "Resume should follow a learner who scrubbed and then stopped."
    expect(worthSending({ positionSeconds: 120, watchedDeltaSeconds: 0 }, 30)).toBe(true);
  });

  it("stays silent when a paused player has not moved", () => {
    // The twin of the case above. Without this, a paused tab reports the same
    // position forever.
    expect(worthSending({ positionSeconds: 120, watchedDeltaSeconds: 0 }, 120)).toBe(false);
  });

  it("sends the first position even with nothing watched", () => {
    // `lastSentPosition === null` means the server has never heard from this
    // tab. A learner who opened a lesson and scrubbed before playing still has
    // a resume point worth keeping.
    expect(worthSending({ positionSeconds: 45, watchedDeltaSeconds: 0 }, null)).toBe(true);
  });

  it("compares rounded positions, as the server stores them", () => {
    // The server rounds before storing, so sub-second drift is not a change.
    // Without the rounding this sends a beat on every animation frame.
    expect(worthSending({ positionSeconds: 120.4, watchedDeltaSeconds: 0 }, 120)).toBe(false);
  });
});
