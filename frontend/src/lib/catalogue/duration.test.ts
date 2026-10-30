import { describe, expect, it } from "vitest";

import { formatCourseDuration } from "./duration";

describe("formatCourseDuration", () => {
  it("renders minutes under an hour", () => {
    expect(formatCourseDuration(25 * 60)).toBe("25 min");
  });

  it("renders whole hours without a stray zero", () => {
    expect(formatCourseDuration(2 * 3600)).toBe("2 hr");
  });

  it("renders hours and minutes together", () => {
    expect(formatCourseDuration(2 * 3600 + 35 * 60)).toBe("2 hr 35 min");
  });

  it("rounds to the nearest minute", () => {
    expect(formatCourseDuration(89)).toBe("1 min");
    expect(formatCourseDuration(91)).toBe("2 min");
  });

  /**
   * ADR-041's decision, enforced on this side of the wire too. The backend
   * withholds a partial total; a formatter that turned `null` into "0 min"
   * would put the number back.
   */
  it("says nothing when the total is unknown", () => {
    expect(formatCourseDuration(null)).toBeNull();
    expect(formatCourseDuration(undefined)).toBeNull();
  });

  it("says nothing rather than zero for an empty or impossible total", () => {
    expect(formatCourseDuration(0)).toBeNull();
    expect(formatCourseDuration(-60)).toBeNull();
    expect(formatCourseDuration(Number.NaN)).toBeNull();
  });

  /**
   * A course shorter than thirty seconds would round to zero. "0 minutes"
   * reads as a bug, not as a short course.
   */
  it("never rounds a real course down to nothing", () => {
    expect(formatCourseDuration(20)).toBe("1 min");
  });
});
