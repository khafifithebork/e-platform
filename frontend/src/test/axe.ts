import axe from "axe-core";

/**
 * Running axe over a rendered fragment, and being honest about what that buys.
 *
 * Adopted under CLAUDE.md §5 on 2026-09-28, resolving the discrepancy ADR-030 §5
 * recorded: architecture.md §8.2 named `@axe-core/react`, `MSW` and `Playwright`
 * and none of the three was installed. The owner approved `axe-core` alone.
 * `axe-core` has **no dependencies of its own** and does not ship to the browser,
 * which is most of why it was the one worth adopting.
 *
 * **`@axe-core/react` was not adopted, and the difference matters.** That package
 * logs findings to the browser console in development — useful for a human
 * watching, useless as a control, because nothing fails. `axe-core` called directly
 * from a test either passes or does not.
 *
 * ## What this cannot do, and what already covers it
 *
 * jsdom has no layout engine and does not apply Tailwind's stylesheet, so any rule
 * that needs computed geometry or real colours cannot run here. Two families are
 * therefore **switched off rather than left to report nothing**, because a rule
 * that silently never fires is worse than no rule:
 *
 * - **`color-contrast`** — `src/app/contrast.test.ts` computes WCAG ratios from the
 *   tokens for both schemes, which is the right way to check a palette defined
 *   entirely in tokens, and it works precisely because it does not need a browser.
 * - **Page-level structure** (`region`, `landmark-one-main`, `page-has-heading-one`,
 *   `html-has-lang`, `bypass`) — a component fragment legitimately has no `<main>`
 *   and no `<h1>`, so these would fail on correct code. `verify:a11y` checks them on
 *   the built HTML of 11 pages, which is where they are real.
 *
 * **So this adds the layer neither of those reaches:** ARIA validity, name and role
 * of a widget, label association, duplicate ids, nesting rules — the things that
 * are wrong in the markup itself rather than in the layout or the palette. That is
 * a narrower claim than "we run axe", and it is the true one.
 */

/** Rules that cannot work in jsdom, or that belong to another check. */
const NOT_APPLICABLE_HERE = [
  "color-contrast",
  "region",
  "landmark-one-main",
  "page-has-heading-one",
  "html-has-lang",
  "html-lang-valid",
  "bypass",
  "document-title",
] as const;

export interface Violation {
  id: string;
  impact: string | null | undefined;
  help: string;
  nodes: string[];
}

/**
 * Every axe violation in `container`, as something a failure message can print.
 *
 * Returns an array rather than throwing, so a test can assert `toEqual([])` and
 * get the offending rule and markup in the diff instead of a stack trace.
 */
export async function axeViolations(container: HTMLElement): Promise<Violation[]> {
  const results = await axe.run(container, {
    rules: Object.fromEntries(NOT_APPLICABLE_HERE.map((id) => [id, { enabled: false }])),
    // `incomplete` findings are things axe could not decide — in jsdom that is
    // mostly anything needing layout. They are not reported as failures here
    // because a check that fails on "cannot tell" fails on everything.
    resultTypes: ["violations"],
  });

  return results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.map((node) => node.html),
  }));
}
