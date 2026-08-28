#!/usr/bin/env node
/**
 * Document structure, checked on the HTML a visitor actually receives.
 *
 * The component tests query the accessibility tree, which is the right place
 * for "is this control labelled". They cannot see the properties that only
 * exist once a whole page is assembled: whether two components each rendered an
 * `<h1>`, whether the heading levels skip because a section was moved, whether
 * a landmark got duplicated by a layout change.
 *
 * Those are the failures that survive a green component suite, and they are
 * why this reads the built output rather than rendering in jsdom.
 *
 * Deliberately no dependency. `axe-core` would find more, and it is a §5
 * decision nobody has made — these are the checks that need nothing but the
 * markup, and they are the ones a page assembly can break.
 *
 * Run after `next build`. Exits non-zero with the offending pages named.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const APP_DIR = join(process.cwd(), ".next", "server", "app");

function htmlFilesIn(dir) {
  let found = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) found = found.concat(htmlFilesIn(path));
    else if (entry.endsWith(".html")) found.push(path);
  }
  return found;
}

/** Strip scripts before looking at markup: the RSC payload is not the page. */
function markup(html) {
  return html.replace(/<script[\s\S]*?<\/script>/g, "");
}

const failures = [];

let pages;
try {
  pages = htmlFilesIn(APP_DIR);
} catch (cause) {
  console.error(
    `Could not read ${APP_DIR}: ${cause.message}\n` +
      `Run \`npm run build\` first — this checks the output of a build.`,
  );
  process.exit(2);
}

// The check that keeps every other check honest.
if (pages.length === 0) {
  console.error("No built pages found. Refusing to report success over an empty list.");
  process.exit(1);
}

for (const page of pages) {
  const name = relative(APP_DIR, page);
  const html = markup(readFileSync(page, "utf8"));

  // Next's own error pages are its markup, not ours, and holding them to this
  // would be reporting a defect nobody here can fix.
  if (name.startsWith("_")) continue;

  const headings = [...html.matchAll(/<h([1-6])[\s>]/g)].map((match) => Number(match[1]));

  const h1s = headings.filter((level) => level === 1).length;
  if (h1s !== 1) {
    failures.push(
      `${name}: ${h1s} <h1> elements — a page needs exactly one, as its title in the ` +
        `heading outline`,
    );
  }

  // A skipped level — h2 straight to h4 — tells a screen-reader user browsing
  // by heading that they missed something. It is the commonest structural
  // defect and it is invisible on screen, because the styling does not follow
  // the level.
  let previous = 0;
  for (const level of headings) {
    if (previous !== 0 && level > previous + 1) {
      failures.push(`${name}: heading level jumps from h${previous} to h${level}`);
      break;
    }
    previous = level;
  }

  const mains = (html.match(/<main[\s>]/g) ?? []).length;
  if (mains !== 1) {
    failures.push(`${name}: ${mains} <main> landmarks — a page needs exactly one`);
  }

  if (!/<html[^>]+lang=/.test(html)) {
    failures.push(
      `${name}: <html> has no lang attribute — a screen reader cannot choose a voice`,
    );
  }

  // Alt is required, empty alt is allowed and means decorative. A missing
  // attribute makes a screen reader read the filename.
  for (const [tag] of html.matchAll(/<img\b[^>]*>/g)) {
    if (!/\balt=/.test(tag)) failures.push(`${name}: <img> without an alt attribute`);
  }
}

if (failures.length > 0) {
  console.error("Document structure problems:\n");
  for (const failure of failures) console.error(`  ${failure}`);
  process.exit(1);
}

console.log(`Document structure is sound across ${pages.length} built pages.`);
