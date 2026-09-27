/**
 * `Button`, and the two properties that are accessibility rather than styling.
 *
 * WCAG 2.2 AA adds **2.5.8 Target Size (Minimum)**: an interactive target must be
 * at least 24 by 24 CSS pixels. ADR-030 found this already satisfied — the
 * smallest control measured in a browser was 34px — and, as with 3.3.8, nothing
 * asserted it, which by ADR-023 §1 means it was not a control.
 *
 * It is worth a guard because the failure is a plausible edit. Someone tightening
 * a dense row reaches for `py-1`, and without a minimum height that is a 26px
 * target at `sm` and shrinking. The enrolment card's resume link was **36px** when
 * it was hand-written, and it only cleared the floor by accident; adopting this
 * primitive is what put it at 40px.
 *
 * Asserted against the variant strings rather than a rendered box. jsdom computes
 * no layout — `getBoundingClientRect` returns zeroes — so a rendered assertion
 * here would be measuring nothing. The numbers are Tailwind's spacing scale, where
 * one unit is 4px.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Button, buttonStyles } from "@/components/ui/Button";

afterEach(() => {
  vi.restoreAllMocks();
});

/** `min-h-11` → 44. Tailwind's scale is 0.25rem per unit, so 4px per unit. */
function minHeightPx(classes: string): number | null {
  const match = classes.match(/\bmin-h-(\d+(?:\.\d+)?)\b/);
  return match ? Number(match[1]) * 4 : null;
}

const SIZES = ["lg", "md", "sm"] as const;

describe("target size (WCAG 2.2 AA, 2.5.8)", () => {
  for (const size of SIZES) {
    it(`${size} declares a minimum height of at least 24px`, () => {
      const height = minHeightPx(buttonStyles({ size }));

      expect(height).not.toBeNull();
      expect(height!).toBeGreaterThanOrEqual(24);
    });
  }

  it("is reading a real minimum and would reject a missing one", () => {
    // The twin. A helper that returned a number regardless would satisfy every
    // assertion above, and one that never matched would return null and fail
    // loudly rather than pass — so both directions are checked here.
    expect(minHeightPx("min-h-11 px-5")).toBe(44);
    expect(minHeightPx("min-h-10 px-3.5")).toBe(40);
    expect(minHeightPx("px-5 py-2.5")).toBeNull();
    expect(minHeightPx("min-h-5")).toBe(20);
  });

  it("keeps the same minimum whether or not the variant draws a border", () => {
    /**
     * `border border-transparent` sits in the base so a bordered variant is not
     * 2px taller than an unbordered one beside it. That was a real defect — the
     * landing page's two calls to action measured 44px and 46px — and the
     * assertion belongs here because a minimum height alone does not fix it: a
     * minimum is a floor, not a cap.
     */
    expect(minHeightPx(buttonStyles({ variant: "primary", size: "lg" }))).toBe(
      minHeightPx(buttonStyles({ variant: "secondary", size: "lg" })),
    );
    expect(buttonStyles({ variant: "primary" })).toContain("border-transparent");
  });
});

describe("the pending state", () => {
  it("tells assistive technology the control is working, not just its label", () => {
    // `aria-busy` rather than a swapped label alone: a screen-reader user should
    // know the control is in progress, and a changed word does not say that.
    render(
      <Button pending pendingLabel="Signing in…">
        Sign in
      </Button>,
    );

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Signing in…");
  });

  it("is not busy or disabled at rest", () => {
    // The twin: a component that always reported busy would pass the test above.
    render(<Button>Sign in</Button>);

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-busy", "false");
    expect(button).not.toBeDisabled();
  });
});
