#!/usr/bin/env node
/**
 * Assert that every public route actually prerendered.
 *
 * **This is invariant 15 checked against the build rather than the source.**
 * The tests in `layout.test.tsx` grep page files for `searchParams`, a `fetch`
 * call, or a `dynamic` export — good proxies, and proxies are all they can be.
 * They cannot see a route that went dynamic for a reason nobody wrote down: a
 * dependency that reads headers, a Next default that changes in a minor
 * release, a `cookies()` call three components deep.
 *
 * Next writes down what it actually did. `app-path-routes-manifest.json` maps
 * source paths — which still carry the `(marketing)` group — to URLs, and
 * `prerender-manifest.json` lists what was prerendered. Comparing them is the
 * only check that cannot be fooled by how the code is written.
 *
 * Run after `next build`. Exits non-zero with the offending routes named.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const NEXT_DIR = join(process.cwd(), ".next");

/** The route group whose pages must never render at request time. */
const GROUP_PREFIX = "/(marketing)/";

function read(name) {
  try {
    return JSON.parse(readFileSync(join(NEXT_DIR, name), "utf8"));
  } catch (cause) {
    console.error(
      `Could not read .next/${name}: ${cause.message}\n` +
        `Run \`npm run build\` first — this checks the output of a build, not the source.`,
    );
    process.exit(2);
  }
}

const appPaths = read("app-path-routes-manifest.json");
const prerender = read("prerender-manifest.json");

const prerendered = new Set(Object.keys(prerender.routes ?? {}));
const dynamicRoutes = prerender.dynamicRoutes ?? {};

const marketing = Object.entries(appPaths).filter(([source]) => source.startsWith(GROUP_PREFIX));

// The check that keeps every other check honest. An empty list satisfies every
// assertion below, and a renamed folder or a changed manifest format would
// produce exactly that — silently, and forever.
if (marketing.length === 0) {
  console.error(
    `No routes found under ${GROUP_PREFIX} in app-path-routes-manifest.json.\n` +
      `Either the route group was renamed or the manifest format changed. ` +
      `Refusing to report success over an empty list.`,
  );
  process.exit(1);
}

const failures = [];

for (const [source, url] of marketing) {
  if (prerendered.has(url)) continue;

  const dynamic = dynamicRoutes[url];

  if (!dynamic) {
    failures.push(`${url}  (${source}) — not prerendered, and not a dynamic segment`);
    continue;
  }

  // A dynamic segment is acceptable only with `dynamicParams = false`, which
  // Next records here as `fallback: false`. Anything else means a slug that
  // `generateStaticParams` did not return gets rendered on demand — a server
  // invocation per request, and how an unpublished course becomes reachable by
  // guessing its slug.
  if (dynamic.fallback !== false) {
    failures.push(
      `${url}  (${source}) — dynamic segment with fallback ${JSON.stringify(dynamic.fallback)}; ` +
        `expected false, i.e. \`export const dynamicParams = false\``,
    );
    continue;
  }

  // `fallback: false` with nothing generated is a route that answers 404 to
  // everything. That is not a violation of invariant 15, but it is always a
  // mistake, and it is what an empty `generateStaticParams` produces when the
  // catalogue read silently returned nothing.
  const generated = [...prerendered].filter((route) =>
    new RegExp(dynamic.routeRegex).test(route),
  );

  if (generated.length === 0) {
    failures.push(
      `${url}  (${source}) — dynamicParams is false and no paths were generated, ` +
        `so every URL under it answers 404`,
    );
  }
}

if (failures.length > 0) {
  console.error(`Public routes that do not prerender (invariant 15):\n`);
  for (const failure of failures) console.error(`  ${failure}`);
  console.error(
    `\nEvery route under ${GROUP_PREFIX} must be static. See CLAUDE.md invariant 15 ` +
      `and docs/specs/m15-public-catalogue.md §4.`,
  );
  process.exit(1);
}

console.log(`All ${marketing.length} public routes prerender:`);
for (const [, url] of marketing) console.log(`  ${url}`);
