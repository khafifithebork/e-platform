import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Reading source files in tests, without reading their comments.
 *
 * **This exists because the same mistake has now been made three times.**
 * Structural checks that grep source are the only way to assert some
 * properties — that no page in a route group opts into dynamic rendering, that
 * no public page states a price, that a component owns a landmark — and every
 * one of them has, at least once, failed against entirely correct code because
 * the file *documented* the rule it was being checked for:
 *
 * - M15's price guard, against a pricing page explaining why it names no price.
 * - M15's `searchParams` guard, against a page explaining why it reads none.
 * - M16 T7's `dangerouslySetInnerHTML` guard, against a transcript panel
 *   explaining why it uses none.
 * - M16 T9's `<main>` guard, against a page explaining that the shell owns it.
 *
 * Each was found by provoking the check and watching it fail on good code, and
 * each was fixed the same way in a different file. This is that fix, once.
 *
 * The opposite failure matters more than the false positive: a check somebody
 * learns to satisfy by rewording a comment has stopped meaning anything.
 */

/** A file's code, with block and line comments removed. */
export function codeOnly(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/**
 * Every `.ts`/`.tsx` file under `dir`, recursively, excluding tests.
 *
 * Tests are excluded because they discuss the code they check — a file
 * asserting "no page calls fetch" necessarily contains the word.
 */
export function sourceFilesIn(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFilesIn(path);
    // `.test.ts` as well as `.test.tsx`. The original excluded only the latter,
    // which matched every test in a route group and so looked correct; a guard
    // scanning a directory of plain `.ts` tests would have been checking the
    // tests along with the code, and the first symptom would be a guard failing
    // against the file that asserts it.
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [path] : [];
  });
}

/** The files under `dir` whose *code* matches `pattern`. */
export function filesMatching(dir: string, pattern: RegExp): string[] {
  return sourceFilesIn(dir).filter((path) => pattern.test(codeOnly(readFileSync(path, "utf8"))));
}
