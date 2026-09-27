/**
 * The theme mechanism, which is two things and only one of them is our colours.
 *
 * `contrast.test.ts` covers the palette — it computes WCAG ratios from the tokens
 * for both schemes. This covers the declaration that decides what the *browser*
 * paints, which no colour arithmetic can reach.
 *
 * **`color-scheme` was missing for the life of the project.** The dark block
 * swaps 17 tokens and two shadows, and that is everything our stylesheet paints.
 * Scrollbars, an `<input>`'s native chrome, a `<select>`'s dropdown, the video
 * element's built-in controls and the autofill background are painted by the
 * browser, which assumes light until a page declares otherwise — so a dark-mode
 * visitor got dark surfaces with light furniture.
 *
 * Found while writing ADR-032, which set out to ask whether the product wanted a
 * manual theme toggle. The answer to that is still open; this half was a defect
 * with no product question attached, so the owner split it out.
 *
 * A one-line declaration is exactly the kind of thing a later reformat or a
 * merge drops without anyone noticing, which is why it is asserted rather than
 * trusted.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

/**
 * The declaration, and **not** `prefers-color-scheme`.
 *
 * The lookbehind is the whole reason this is a named constant. Written as a bare
 * `/color-scheme\s*:/`, every assertion below matched the `@media (prefers-color-scheme: dark)`
 * query instead — so the "is it declared" test **passed with the declaration
 * absent**, and the "which value" test read `dark)` plus whatever followed it and
 * failed against a correct stylesheet. One of the two failing is how it was
 * caught; the one that silently passed is the one that mattered.
 */
const DECLARATION = /(?<!prefers-)color-scheme\s*:/;

/** `globals.css` with comments stripped, so prose about a rule is not the rule. */
function code(): string {
  return CSS.replace(/\/\*[\s\S]*?\*\//g, "");
}

describe("color-scheme", () => {
  it("is declared", () => {
    // The whole point. Without it the browser paints its own furniture light.
    expect(code()).toMatch(DECLARATION);
  });

  it("declares support for both schemes rather than forcing one", () => {
    /**
     * `light dark` and not `light` or `dark` alone.
     *
     * A single value tells the browser which scheme the page *is*, overriding
     * the visitor's own preference — the opposite of what ADR-032 keeps, which
     * is that the operating system decides. Both values say "this page handles
     * either, follow the user".
     */
    // `String.raw`, because `"\s"` in a JS string literal is just `s` — the
    // pattern would then mean "zero or more literal s" and match by luck.
    const match = code().match(new RegExp(DECLARATION.source + String.raw`\s*([^;}]+)`));

    expect(match).not.toBeNull();
    const value = match![1].trim();

    expect(value.split(/\s+/).sort()).toEqual(["dark", "light"]);
  });

  it("is on :root, so it applies to the whole document", () => {
    // On `body` it would still mostly work, but the scrollbar of the root
    // scrolling element is resolved from the root element — which is the
    // scrollbar most visible on a long catalogue page.
    expect(code()).toMatch(/:root\s*\{[^}]*(?<!prefers-)color-scheme\s*:/);
  });

  it("is not satisfied by a comment mentioning it", () => {
    /**
     * The twin, and it is not theoretical here. This file's own docstring names
     * `color-scheme` repeatedly, and `src/test/source.ts` documents four
     * occasions where a structural check passed or failed against prose rather
     * than code. Stripping comments is the fix, and this proves it happens.
     */
    const commentOnly = "/* color-scheme: light dark; */\n:root { color: red; }";
    const stripped = commentOnly.replace(/\/\*[\s\S]*?\*\//g, "");

    expect(stripped).not.toMatch(DECLARATION);
  });
});

describe("the dark scheme is still driven by the system", () => {
  it("redefines tokens inside a prefers-color-scheme query", () => {
    // ADR-032's decision, pinned: no manual toggle, no `data-theme` attribute,
    // no stored preference. If a toggle is ever added it supersedes that ADR
    // explicitly, and this assertion is where that change becomes visible.
    expect(code()).toMatch(/@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)/);
    expect(code()).not.toMatch(/\[data-theme/);
  });
});
