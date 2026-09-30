/**
 * What a share card says.
 *
 * **The routes themselves are not tested here, and cannot usefully be.**
 * `ImageResponse` returns a PNG stream produced by WASM; jsdom cannot render it and
 * reading the bytes would assert nothing about whether the card is legible. So every
 * decision that *can* be checked lives in `card.ts`, and the build is what proves the
 * images exist — `next build` reports the three routes, and their `.body` files start
 * with the PNG magic number.
 */

import { describe, expect, it } from "vitest";

import type { PublicCourseDetail } from "@/lib/catalogue/courses";
import { MAX_TITLE, courseCardText, fit } from "@/lib/share/card";

function course(overrides: Partial<PublicCourseDetail> = {}): PublicCourseDetail {
  return {
    title: "Spanish for beginners",
    slug: "spanish",
    description: "",
    language: { code: "es", name: "Spanish", native_name: "Español" },
    level: "A1",
    ...overrides,
  } as PublicCourseDetail;
}

describe("fitting a title", () => {
  it("leaves a short title alone", () => {
    expect(fit("Spanish for beginners")).toBe("Spanish for beginners");
  });

  it("trims surrounding whitespace, which a card would render as a gap", () => {
    expect(fit("  Spanish  ")).toBe("Spanish");
  });

  it("cuts a long title at a word boundary rather than mid-word", () => {
    /**
     * The catalogue allows a 200-character title, which would overflow a 1200×630
     * card entirely. Cutting in the renderer instead means discovering the limit from
     * a screenshot.
     */
    const long =
      "Conversational Spanish for travellers who already know some grammar and want practice";

    const result = fit(long);

    expect(result.length).toBeLessThanOrEqual(MAX_TITLE + 1);
    expect(result.endsWith("…")).toBe(true);

    /**
     * The property is that the kept text ends where a word ends — so it is a prefix
     * of the original *and* the original's next character is a space.
     *
     * The first attempt asserted `not.toMatch(/[a-z]…$/i)`, which failed against
     * entirely correct output: "…for travellers…" ends in a letter because it ends in
     * a complete word. A regex on the last character cannot tell a finished word from
     * a severed one; only comparing against the original can.
     */
    const kept = result.slice(0, -1);
    expect(long.startsWith(kept)).toBe(true);
    expect(long.charAt(kept.length)).toBe(" ");
  });

  it("cuts mid-word rather than losing most of the title to a long word", () => {
    // A word boundary is preferred, not required: backing up to the last space would
    // otherwise throw away half the card when one word is very long.
    const result = fit("Anticonstitutionnellement" + "x".repeat(80));

    expect(result.length).toBeLessThanOrEqual(MAX_TITLE + 1);
    expect(result.endsWith("…")).toBe(true);
  });

  it("does not add an ellipsis to a title that exactly fits", () => {
    const exact = "a".repeat(MAX_TITLE);

    expect(fit(exact)).toBe(exact);
  });
});

describe("a course's card", () => {
  it("says the language and the level, spelled out", () => {
    expect(courseCardText(course()).subtitle).toBe("Spanish · A1 · Beginner");
  });

  it("falls back to the bare code for a level it does not know", () => {
    // A level added server-side degrades to what it already was, rather than
    // rendering `undefined` onto an image nobody can edit afterwards.
    expect(courseCardText(course({ level: "D3" as never })).subtitle).toBe("Spanish · D3");
  });

  it("does not use the description, which is often empty", () => {
    /**
     * `t8-spanish` has `description: ""` today, so a card built on it would be blank
     * — and a long one would overflow. The language and level are always present and
     * are what somebody deciding whether to open a shared link wants.
     */
    const described = courseCardText(course({ description: "A long description here." }));
    const bare = courseCardText(course({ description: "" }));

    expect(described).toEqual(bare);
  });

  it("fits the title, so a long one cannot overflow the card", () => {
    const result = courseCardText(course({ title: "x".repeat(200) }));

    expect(result.title.length).toBeLessThanOrEqual(MAX_TITLE + 1);
  });
});
