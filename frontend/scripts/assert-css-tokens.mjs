#!/usr/bin/env node
/**
 * Every design token a class references actually reaches the stylesheet.
 *
 * **This exists because 45 utility classes across 15 components had never once
 * applied.** Tailwind 4 reads `rounded-(--radius-md)` as `var(--radius-md)` and
 * `rounded-[--radius-md]` as the literal value `--radius-md`:
 *
 *     .rounded-\(--radius-md\) { border-radius: var(--radius-md) }   ← 12px
 *     .rounded-\[--radius-md\] { border-radius: --radius-md }        ← dropped
 *
 * The second is not valid CSS, so the browser discards the declaration and the
 * element renders with no radius at all. The bracket form is how Tailwind 3
 * spelled it, this project has been on `^4` since its first frontend commit,
 * and every use of it was written by somebody who could not see that it did
 * nothing. Measured on `/login`, where the submit button (paren form) computed
 * `border-radius: 12px` while the two inputs directly above it (bracket form)
 * computed `0px`.
 *
 * **Why this reads the compiled CSS rather than grepping the source.** A source
 * check — and there is one, in `src/test/css-tokens.test.ts` — can only look for
 * the one spelling already known to be wrong. This asserts the property itself:
 * no declaration anywhere in the output may have a bare custom-property *name*
 * as its value. That covers every utility, every property, and any future
 * syntax slip nobody has thought of yet, including ones Tailwind may introduce.
 *
 * Neither check replaces the other. The source one fails in a second without a
 * build; this one is the check that is actually about the rendered result.
 *
 * **A comment can fail this, and that is correct rather than a false positive.**
 * Tailwind's source detection cannot tell code from prose, so a `src/` file that
 * merely *mentions* `rounded-[--radius-md]` in a docstring compiles an invalid
 * rule into the stylesheet exactly as a real class would. `Button.tsx` proves the
 * mechanism harmlessly: its comment names `focus-visible:outline-none` and the
 * built CSS contains a rule for it, used by nothing.
 *
 * So the broken form must not appear in any *scanned* file, prose included. The
 * two places it legitimately does are both outside the scan: this script, which
 * lives in `scripts/`, and `src/test/css-tokens.test.ts`, which needs the literal
 * strings to prove its pattern matches them and is covered by the `@source not`
 * exclusion in `globals.css`. That exclusion is load-bearing for this check, not
 * only a bundle-size nicety.
 *
 * Deliberately no dependency — no CSS parser. The declarations this looks for
 * have a shape a scanner can find exactly: `: --name` with nothing else in the
 * value. A parser would be a §5 decision to buy precision that is not needed.
 *
 * Run after `next build`. Exits non-zero with the offending rules named.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const NEXT_DIR = join(process.cwd(), ".next");

function cssFilesIn(dir) {
  let found = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    // `.next/dev` holds a development build's chunks. Including it would let a
    // stale dev artifact decide the result of a check on a production build.
    if (entry === "dev") continue;
    if (statSync(path).isDirectory()) found = found.concat(cssFilesIn(path));
    else if (entry.endsWith(".css")) found.push(path);
  }
  return found;
}

/**
 * Declarations whose value is a bare custom-property name.
 *
 * `--tw-shadow:--shadow-sm` and `border-radius:--radius-lg` both match; a real
 * custom-property *definition* like `--radius-md:12px` does not, because the
 * value has to start with `--` for this to fire. `var(--x)` does not match
 * either, which is the whole point — that is the correct form.
 */
const BARE_TOKEN_VALUE = /([-a-z]+)\s*:\s*(--[a-z0-9-]+)\s*(?=[;}])/gi;

let files;
try {
  files = cssFilesIn(NEXT_DIR);
} catch (cause) {
  console.error(
    `Could not read ${NEXT_DIR}: ${cause.message}\n` +
      `Run \`npm run build\` first — this checks the output of a build.`,
  );
  process.exit(2);
}

// The check that keeps the check honest. An empty file list matches nothing and
// would otherwise report success over having looked at nothing at all.
if (files.length === 0) {
  console.error("No built CSS found. Refusing to report success over an empty list.");
  process.exit(1);
}

const failures = [];
const sourceCSS = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");
const lightTheme = sourceCSS.match(/@theme\s*\{([^}]+)\}/)?.[1] ?? "";
const lightColors = new Map([...lightTheme.matchAll(/(--color-[\w-]+)\s*:\s*(#[a-f\d]{6})/gi)].map(([, name, value]) => [name, value]));

{
  const css = files.map((file) => readFileSync(file, "utf8")).join("\n");
  // Inspect the emitted rule, not just a source media query that Tailwind may
  // hoist away. Fail closed if the expected root/media structure changes.
  const darkRoot = /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]+)\}\s*\}/g;
  const darkBlocks = [...css.matchAll(darkRoot)];
  if (!darkBlocks.some((match) => /--color-ink\s*:/.test(match[1]))) {
    failures.push("Dark theme token overrides are missing from their compiled media query.");
  }
  const unconditional = css.replace(darkRoot, "");
  for (const [, declarations] of unconditional.matchAll(/:root(?:\s*,\s*:host)?\s*\{([^}]+)\}/g)) {
    for (const [, name, value] of darkBlocks.flatMap((match) =>
      [...match[1].matchAll(/(--color-[\w-]+)\s*:\s*(#[a-f\d]{6})/gi)],
    )) {
      if (lightColors.get(name) !== value && declarations.includes(`${name}:${value}`)) {
        failures.push(`Dark override ${name} leaked into an unconditional root rule.`);
      }
    }
  }
}

for (const file of files) {
  const css = readFileSync(file, "utf8");
  for (const [, property, value] of css.matchAll(BARE_TOKEN_VALUE)) {
    // A custom property may legitimately be *assigned* another custom
    // property's name as a value — `--a:--b` is valid CSS and means the string
    // `--b`. Nothing in this project does that, and Tailwind emits it only as
    // the symptom being checked for, so it is reported rather than exempted.
    failures.push(`${property}: ${value}  — should be ${property}: var(${value})`);
  }
}

if (failures.length > 0) {
  console.error(
    "CSS integrity failures: invalid token references or misplaced theme overrides.\n" +
      "Bare token values need var(--token); dark overrides must retain their media condition.\n",
  );
  for (const failure of new Set(failures)) console.error(`  ${failure}`);
  process.exit(1);
}

/**
 * Rules that must survive compilation, and which nothing else would notice losing.
 *
 * **CSS has vanished silently from this project's output twice.** 45 token classes
 * written in Tailwind 3's `-[--token]` spelling compiled to declarations the browser
 * drops, and a hand-written `@media (width < 80rem)` block disappeared whole — the
 * rules either side of it survived, so nothing looked wrong. Neither had an error,
 * a warning, or a failing test.
 *
 * So a rule that cannot be checked any other way gets checked here. `::cue` styles
 * the text inside a `<track>`, which the browser draws in a shadow tree: no test can
 * query it, no component renders it, and jsdom has no captions at all. Its only
 * observable property is that it reached the stylesheet.
 */
const MUST_SURVIVE = [
  { selector: "::cue", why: "caption legibility over video — nothing else can see it" },
  { selector: ".course-progress::-webkit-progress-value", why: "native course progress uses semantic indigo" },
  { selector: ".course-progress::-moz-progress-bar", why: "Firefox native course progress uses semantic indigo" },
];

const missing = MUST_SURVIVE.filter(
  ({ selector }) => !files.some((file) => readFileSync(file, "utf8").includes(selector)),
);

if (missing.length > 0) {
  console.error(
    "Rules that should be in the compiled CSS are not.\n" +
      "CSS has disappeared from this build twice before without any error.\n",
  );
  for (const { selector, why } of missing) console.error(`  ${selector}  — ${why}`);
  process.exit(1);
}

console.log(
  `Every token reference resolves: ${files.length} stylesheet(s) checked, ` +
    `no bare custom-property values, ${MUST_SURVIVE.length} pinned rule(s) present.`,
);
