#!/usr/bin/env node
/**
 * Per-route first-load weight, against a ceiling.
 *
 * `docs/specs/frontend-state-and-api.md` §11 proposed **350 KB gzipped per route**
 * and said enforcing it "needs the owner" and "should be a script beside
 * `verify:static` and `verify:css` rather than a number in a document nobody runs".
 * Approved 2026-10-03. This is that script.
 *
 * ## The method is the measurement's, deliberately unchanged
 *
 * For each prerendered page, the unique `<script src>` and stylesheet references are
 * resolved to files and gzipped at level 9. That is what a browser downloads on a
 * cold visit to that route — not an estimate, and not a sum of all chunks.
 *
 * **Reproducing §11's method exactly is the whole point.** The figures in that table
 * only mean something if the gate measures the same way; a different method would
 * produce a different number and read as a regression on the first run. Two
 * measurements already exist to compare against — 2026-09-28 and 2026-09-30 — and
 * `npm run verify:bundle` must agree with the later one.
 *
 * ## What the number is, and what it is not
 *
 * 350,000 bytes, in the units §11's table uses: it reports 327,284 bytes as "327 KB",
 * so a kilobyte is 1000 bytes here. At the time of approval the worst route was
 * **327 KB, leaving about 7%**.
 *
 * **That headroom is for a dependency, not for features.** Seven batches of the
 * quality addendum moved the worst route by 1.3 KB — 0.4% — so ordinary work does not
 * approach this. A gate that fires is far more likely to mean something arrived in the
 * shared chunks than that somebody wrote too much code.
 *
 * ## What it cannot cover
 *
 * **The lesson route.** It is the only dynamic route (ADR-026), so it has no
 * prerendered HTML to read, and it is the route a learner actually waits on. §11 says
 * its first load "has to be measured in a browser's network panel — which makes it a
 * person's job". This gate does not cover it and must not be read as if it did.
 *
 * Run after `next build`. Exits non-zero naming every route over the ceiling.
 */

import { gzipSync } from "node:zlib";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/** 350 KB, where a kilobyte is 1000 bytes — the units §11's table reports in. */
const BUDGET_BYTES = 350_000;

const NEXT_DIR = join(process.cwd(), ".next");
const APP_DIR = join(NEXT_DIR, "server", "app");

function htmlFilesIn(dir) {
  let found = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) found = found.concat(htmlFilesIn(path));
    else if (entry.endsWith(".html")) found.push(path);
  }
  return found;
}

/** `/_next/static/chunks/x.js` → the file on disk, or null when it is not ours. */
function resolveAsset(url) {
  const clean = url.split("?")[0];
  if (!clean.startsWith("/_next/")) return null;

  const path = join(NEXT_DIR, clean.slice("/_next/".length));
  return existsSync(path) ? path : null;
}

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

/**
 * The check that keeps the check honest.
 *
 * An empty page list weighs nothing and would pass every budget. The same floor every
 * other script here carries, for the same reason.
 */
if (pages.length === 0) {
  console.error("No built pages found. Refusing to report success over an empty list.");
  process.exit(1);
}

const rows = [];

for (const page of pages) {
  const html = readFileSync(page, "utf8");
  const name = "/" + relative(APP_DIR, page).replaceAll("\\", "/").replace(/\.html$/, "");

  const refs = new Set();
  for (const [, src] of html.matchAll(/<script[^>]+src="([^"]+)"/g)) refs.add(src);
  for (const [, href] of html.matchAll(/<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/g)) {
    refs.add(href);
  }
  // Both attribute orders: Next has emitted each, and matching only one silently
  // undercounts the stylesheet on every route.
  for (const [, href] of html.matchAll(/<link[^>]+href="([^"]+)"[^>]+rel="stylesheet"/g)) {
    refs.add(href);
  }

  let total = 0;
  let assets = 0;

  for (const ref of refs) {
    const file = resolveAsset(ref);
    if (file === null) continue;

    total += gzipSync(readFileSync(file), { level: 9 }).length;
    assets += 1;
  }

  rows.push({ name, total, assets });
}

/**
 * A second floor, on the assets rather than the pages.
 *
 * A page whose script references stopped matching would weigh zero and pass. Every
 * route in this application loads at least eight chunks — `_global-error`, the
 * lightest by design, loads exactly eight — so a page resolving none means the
 * matcher broke rather than that the page is weightless.
 */
const weightless = rows.filter((row) => row.assets === 0).map((row) => row.name);
if (weightless.length > 0) {
  console.error(
    "Pages whose assets could not be resolved at all — the matcher has stopped " +
      `matching, not the pages stopped loading code:\n  ${weightless.join("\n  ")}`,
  );
  process.exit(1);
}

rows.sort((a, b) => b.total - a.total);
const over = rows.filter((row) => row.total > BUDGET_BYTES);

const kb = (bytes) => `${(bytes / 1000).toFixed(1)} KB`;

if (over.length > 0) {
  console.error(
    `Routes over the ${kb(BUDGET_BYTES)} gzipped first-load budget:\n`,
  );
  for (const row of over) {
    console.error(`  ${row.name}  ${kb(row.total)}  (+${kb(row.total - BUDGET_BYTES)})`);
  }
  console.error(
    "\nSeven batches of feature work moved the worst route by 1.3 KB, so this is far " +
      "more likely to be a dependency than code you just wrote. " +
      "docs/specs/frontend-state-and-api.md §11 has the method and the baselines.",
  );
  process.exit(1);
}

const worst = rows[0];
console.log(
  `First-load budget met across ${rows.length} routes. ` +
    `Worst: ${worst.name} at ${kb(worst.total)}, ` +
    `${kb(BUDGET_BYTES - worst.total)} under the ${kb(BUDGET_BYTES)} ceiling.`,
);
