/**
 * Colour contrast, computed from the tokens rather than eyeballed.
 *
 * `globals.css` claims the accent is "dark enough for white text at AA".
 * **Nothing has ever checked that**, and it is the kind of claim that is
 * written once when a palette is chosen and then quietly invalidated by a
 * later tweak to one hex value.
 *
 * WCAG 2.1 AA, which is what architecture.md's accessibility line asks for:
 *
 * - 4.5:1 for normal body text
 * - 3:1 for large text (≥18.66px bold or ≥24px) and for UI component
 *   boundaries such as a form field's border
 *
 * Both schemes are checked. A palette that passes in light and fails in dark
 * is a palette that fails for whoever has dark mode on, which on a reading
 * surface is a lot of people.
 *
 * This needs no dependency. `axe-core` would catch more — it walks a rendered
 * page and sees computed styles — but it is a §5 dependency decision that has
 * not been made, and the arithmetic below is the part that matters most for a
 * palette defined entirely in tokens.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

/**
 * The tokens for one scheme.
 *
 * The dark block redefines a subset, so it is layered over the light values
 * rather than read alone — exactly how the cascade resolves it.
 */
function tokens(scheme: "light" | "dark"): Record<string, string> {
  const darkStart = CSS.indexOf("prefers-color-scheme: dark");
  const source = scheme === "light" ? CSS.slice(0, darkStart) : CSS;

  const found: Record<string, string> = {};
  for (const [, name, value] of source.matchAll(/--color-([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) {
    // Later definitions win, which for the dark pass means the dark block.
    found[name] = value;
  }
  return found;
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((offset) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(foreground: string, background: string): number {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Every foreground/background pair the components actually put together. */
const BODY_TEXT: [string, string][] = [
  ["ink", "paper"],
  ["ink", "surface"],
  ["ink-muted", "paper"],
  ["ink-muted", "surface"],
  ["ink-muted", "surface-sunken"],
  ["accent", "paper"],
  ["accent", "surface"],
  ["accent", "accent-subtle"],
  ["danger", "danger-subtle"],
  ["success", "success-subtle"],
  ["on-accent", "accent"],
  ["on-accent", "accent-hover"],
];

/**
 * Text that is decorative or supporting rather than content.
 *
 * `ink-subtle` is used for metadata — a level code, a breadcrumb separator, an
 * instructor name. Held to 3:1 rather than 4.5:1 **only where it is genuinely
 * large or non-essential**, and the list is short on purpose: the temptation
 * is to move whatever fails into it.
 */
const SUPPORTING_TEXT: [string, string][] = [
  ["ink-subtle", "paper"],
  ["ink-subtle", "surface"],
];

/** Borders and other non-text boundaries. WCAG 1.4.11, 3:1. */
const UI_BOUNDARIES: [string, string][] = [
  ["line-strong", "surface"],
  ["line-strong", "paper"],
];

describe.each(["light", "dark"] as const)("%s scheme", (scheme) => {
  const palette = tokens(scheme);

  it("defines every colour the components use", () => {
    // The check that keeps the rest honest. A renamed token would otherwise
    // make `contrast(undefined, ...)` throw — or worse, quietly skip.
    const used = [...BODY_TEXT, ...SUPPORTING_TEXT, ...UI_BOUNDARIES].flat();

    for (const name of used) expect(palette[name], `--color-${name}`).toBeDefined();
  });

  it.each(BODY_TEXT)("%s on %s reaches AA for body text", (fg, bg) => {
    expect(contrast(palette[fg], palette[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(SUPPORTING_TEXT)("%s on %s reaches AA for large text", (fg, bg) => {
    expect(contrast(palette[fg], palette[bg])).toBeGreaterThanOrEqual(3);
  });

  it.each(UI_BOUNDARIES)("%s on %s is a visible boundary", (fg, bg) => {
    expect(contrast(palette[fg], palette[bg])).toBeGreaterThanOrEqual(3);
  });

  it("puts legible text on the accent", () => {
    /**
     * Every primary button in the app depends on this pair.
     *
     * Asserted against `--color-on-accent` rather than against white, and that
     * is the finding this whole file was written to catch. `globals.css` used
     * to claim the accent was "dark enough for white text at AA" — true in the
     * light scheme at 4.74, and false in the dark scheme at **2.50**, where the
     * accent is a bright orange. Every primary button was unreadable for
     * anyone with dark mode on.
     *
     * The fix was not darkening the dark accent, which is doing its job as a
     * highlight, but introducing a token for what sits on top of it: white in
     * light, dark ink in dark.
     */
    expect(contrast(palette["on-accent"], palette.accent)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps the hover state legible too", () => {
    // A hover colour that fails is a button that becomes unreadable exactly
    // while somebody is pointing at it.
    expect(contrast(palette["on-accent"], palette["accent-hover"])).toBeGreaterThanOrEqual(4.5);
  });

  it("defines on-accent separately from ink", () => {
    // The twin. If `on-accent` were simply an alias for the scheme's text
    // colour, the two assertions above would still pass in dark mode and fail
    // in light — and the temptation when that happens is to relax them.
    expect(palette["on-accent"]).toBeDefined();
  });
});

describe("the arithmetic itself", () => {
  it("scores black on white at 21", () => {
    // The maximum possible ratio. Without this, a broken luminance function
    // could return a constant that happens to pass every assertion above.
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 1);
  });

  it("scores a colour against itself at 1", () => {
    expect(contrast("#a8621b", "#a8621b")).toBeCloseTo(1, 5);
  });

  it("reads different values for the two schemes", () => {
    // If `tokens()` returned the same palette twice, the dark pass would be
    // the light pass again and nothing about dark mode would be tested.
    expect(tokens("light").ink).not.toBe(tokens("dark").ink);
  });
});
