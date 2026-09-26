/**
 * The provider that replaced ten render-time branches.
 *
 * Losing it would not blank the page the way the old branches did — the
 * components no longer decide anything during render — but it would silently
 * give every visitor the full motion treatment, including the ones whose
 * operating system has asked for less. That is a quiet accessibility
 * regression with no visible symptom on the machine of whoever caused it,
 * which is the same property that let the original bug ship.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MotionProvider } from "@/components/motion/MotionProvider";

const ROOT_LAYOUT = join(import.meta.dirname, "..", "..", "app", "layout.tsx");

describe("MotionProvider", () => {
  it("renders its children", () => {
    render(
      <MotionProvider>
        <p>Wrapped.</p>
      </MotionProvider>,
    );

    expect(screen.getByText("Wrapped.")).toBeInTheDocument();
  });

  it("asks Motion to respect the visitor's preference", () => {
    // `"user"` and not `"always"`: the point is to follow the setting, not to
    // impose reduced motion on everybody. Read from source because the config
    // is a context value with no rendered output to assert on.
    const source = readFileSync(
      join(import.meta.dirname, "MotionProvider.tsx"),
      "utf8",
    );

    expect(source).toContain('reducedMotion="user"');
  });

  it("is mounted in the root layout, wrapping the whole tree", () => {
    /**
     * At the root rather than per-route, because reduced motion is a property
     * of the visitor and not of a page — and because the bug it replaces was
     * ten components each answering that question for themselves.
     */
    const layout = readFileSync(ROOT_LAYOUT, "utf8");

    expect(layout).toContain("MotionProvider");
    expect(layout).toMatch(/<MotionProvider>\s*\{children\}\s*<\/MotionProvider>/);
  });
});
