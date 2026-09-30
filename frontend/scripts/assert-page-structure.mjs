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

/**
 * Whether a built page is one a stranger can reach and might share.
 *
 * Matched by shape rather than by a list of slugs: pinning `courses/t8-spanish.html`
 * would tie this to seeded data, and the day that seed changed the check would match
 * nothing and pass. The counter below is what notices if this stops matching at all.
 */
function isPublic(name) {
  const path = name.replaceAll("\\", "/");

  return (
    path === "index.html" ||
    path === "courses.html" ||
    path === "pricing.html" ||
    /^courses\/[^/]+\.html$/.test(path)
  );
}

let publicPagesSeen = 0;
let jsonLdBlocksSeen = 0;
let linksSeen = 0;

/**
 * The one route served without a prerendered file: the lesson player (ADR-026).
 *
 * The course slug is captured on purpose — the lesson has no file but the course
 * does, so half of a dynamic path stays checkable. A second entry here is how this
 * check would get quietly weaker, and should come with the reason that route cannot
 * be a file.
 */
const DYNAMIC_LESSON = /^\/courses\/([^/]+)\/lessons\/[^/]+\/?$/;

/** Destinations that mean "not wired yet" and must not reach a built page. */
const PLACEHOLDER_HREFS = new Set(["#", "", "/todo", "/TODO", "javascript:void(0)"]);
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

/**
 * Every built page, by path relative to the app directory, for resolving links.
 *
 * Built before the loop rather than inside it: resolving a link means asking whether
 * *any* page exists at that path, which needs the whole set.
 */
const builtPages = new Set(
  pages.map((page) => relative(APP_DIR, page).replaceAll("\\", "/")),
);

// The check that keeps every other check honest.
if (pages.length === 0) {
  console.error("No built pages found. Refusing to report success over an empty list.");
  process.exit(1);
}

for (const page of pages) {
  const name = relative(APP_DIR, page);
  /**
   * Both forms, and the distinction matters.
   *
   * `markup()` strips every `<script>` before the structural checks, because the RSC
   * payload is not the page — without that, its serialised props would be searched
   * for headings and `<img>` tags. The JSON-LD check needs the opposite: it is *only*
   * interested in a script element, so it reads the raw file.
   *
   * The floor check below caught this the first time it ran: the JSON-LD matcher was
   * pointed at the stripped copy and matched nothing, which without a floor would
   * have reported success over having looked at nothing.
   */
  const raw = readFileSync(page, "utf8");
  const html = markup(raw);

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

  /**
   * Every public page carries a share image, and this check exists because nothing
   * else could see it going missing.
   *
   * **`opengraph-image.tsx` contributes `og:image` to the segment it sits in**, and
   * Next merges metadata *shallowly*: a page that sets its own `openGraph` object
   * **replaces** the parent's, image included. `publicMetadata` did exactly that from
   * PR #96 until 2026-09-30, which silently stripped `og:site_name` and `og:locale`
   * from all four public pages — and would have stripped `og:image` the moment one
   * existed.
   *
   * It was invisible to every test in the repository, because the unit tests read the
   * metadata object each page *sets* and the fault was in what the object *removed*.
   * Only assembled HTML shows it, which is what this script reads.
   *
   * Scoped to the public pages: the authenticated ones are `Disallow`ed in robots.txt
   * and nobody shares a link to a sign-in form.
   */
  if (isPublic(name)) {
    publicPagesSeen += 1;

    if (!/<meta property="og:image"/.test(html)) {
      failures.push(`${name}: no og:image — a shared link to this page has no card`);
    }
    if (!/<meta property="og:site_name"/.test(html)) {
      failures.push(
        `${name}: no og:site_name — check whether a page-level openGraph object ` +
          `replaced the root layout's`,
      );
    }
  }

  /**
   * Structured data, checked on the assembled HTML because that is the only place
   * its most important property exists.
   *
   * A course title and description are user-supplied — instructor-authored, then
   * admin-approved — and they are serialised into a `<script>` element. The sequence
   * that could terminate that element early is `</script`, and **React's server
   * renderer escapes it**: a title containing `</script>` comes out as
   * `</\u0073cript>`. That escaping happens in `react-dom/server` and nowhere else,
   * so no jsdom test can observe it; a unit test would set text through the DOM,
   * where no parser is involved and nothing needs escaping.
   *
   * So: every block must parse as JSON, and none may contain a raw `</script`.
   * `structured-data.test.ts` covers what the object *says*; this covers whether it
   * survives being written into a page.
   */
  for (const [, body] of raw.matchAll(
    /<script type="application\/ld\+json">([\s\S]*?)<\/script>/g,
  )) {
    jsonLdBlocksSeen += 1;

    if (/<\/script/i.test(body)) {
      failures.push(
        `${name}: a JSON-LD block contains a raw </script — it can terminate the ` +
          `element early, which is script injection`,
      );
      continue;
    }

    try {
      const parsed = JSON.parse(body);
      if (parsed["@context"] !== "https://schema.org") {
        failures.push(`${name}: JSON-LD has no schema.org @context`);
      }
    } catch (cause) {
      failures.push(`${name}: JSON-LD does not parse — ${cause.message}`);
    }
  }

  /**
   * Internal links point at something that exists.
   *
   * **The fault this catches has already happened here twice.** Batch one added a
   * link to `/verify-email` from the registration confirmation; had the order been
   * reversed, that link would have shipped pointing at a 404 and nothing would have
   * objected. Batch two's `robots.txt` list is the same shape of problem caught by a
   * different check. A link to a page that does not exist is worse than an absent
   * link, because it looks like a feature.
   *
   * Only internal, non-dynamic hrefs. `mailto:`, `tel:`, external URLs, fragments and
   * query strings are all somebody else's to resolve — and there is nothing to
   * resolve them against at build time.
   *
   * **A dynamic route cannot be checked by filename**, so `/courses/<slug>` resolves
   * against the built pages rather than against the route pattern: if the slug was
   * prerendered there is a file, and if it was not, the link is genuinely broken.
   *
   * Placeholder destinations are refused outright. `href="#"`, `href=""` and
   * `href="/todo"` are all "I will wire this later" written into shipped markup.
   */
  let linksOnThisPage = 0;

  for (const [, href] of html.matchAll(/<a\b[^>]+href="([^"]*)"/g)) {
    linksSeen += 1;
    linksOnThisPage += 1;

    if (PLACEHOLDER_HREFS.has(href)) {
      failures.push(`${name}: <a href="${href}"> is a placeholder destination`);
      continue;
    }

    // Anything not a plain internal path is out of scope: protocol-relative and
    // absolute URLs, fragments, mail and tel.
    if (!href.startsWith("/") || href.startsWith("//")) continue;

    const path = href.split("#")[0].split("?")[0];
    if (path === "/" || path === "") continue;

    /**
     * Two things this check cannot resolve by filename, and both are real.
     *
     * **`/api/*` is Django.** `next.config.ts` rewrites it, so there is no Next page
     * and never will be — the destination is another service. Found by this check on
     * its first run, on the data-export link.
     *
     * **The lesson route is dynamic** (ADR-026), so it has no prerendered HTML at
     * all. Also found on the first run. A pattern is the only way to accept it, and a
     * pattern is weaker than a file: if the route moves, this keeps accepting the old
     * shape. Kept to one entry, named, and pointed at the ADR so the weakness is
     * visible rather than implied.
     */
    if (path.startsWith("/api/")) continue;

    const dynamic = path.match(DYNAMIC_LESSON);
    if (dynamic) {
      /**
       * The lesson has no file, but **the course does** — so the half that can be
       * resolved is resolved.
       *
       * **Found by provoking**: the first version accepted the whole pattern, so
       * `/courses/ghost/lessons/one/` passed even though no `ghost` course was ever
       * built. A link to a lesson under a course that does not exist is a broken link.
       */
      const courseSlug = dynamic[1];
      if (!builtPages.has(`courses/${courseSlug}.html`)) {
        failures.push(
          `${name}: <a href="${href}"> is a lesson under a course with no built page ` +
            `(courses/${courseSlug}.html)`,
        );
      }
      continue;
    }

    // `trailingSlash: true`, so `/courses/` is the canonical form and either spelling
    // resolves to the same built file.
    const bare = path.replace(/\/$/, "").replace(/^\//, "");
    const candidates = [`${bare}.html`, `${bare}/index.html`];

    if (!candidates.some((candidate) => builtPages.has(candidate))) {
      failures.push(
        `${name}: <a href="${href}"> has no built page — expected one of ` +
          candidates.join(" or "),
      );
    }
  }

  /**
   * Per page, not only in total — and **provoking is why this exists**.
   *
   * Stripping every `href` from one page left the overall count well above its floor,
   * because twelve other pages still had links: a matcher that stopped working on one
   * page would have gone unnoticed. Every page here wears either `SiteShell` or the
   * auth shell, and both carry navigation, so a page with no links at all means the
   * matcher broke rather than that the page is bare.
   */
  if (linksOnThisPage === 0) {
    failures.push(`${name}: no links found at all — the matcher has stopped matching`);
  }
}

/**
 * And in total, which catches the loop breaking everywhere at once.
 *
 * Weaker than the per-page check above and kept anyway: a change that removed the
 * loop entirely would satisfy a per-page check vacuously, because there would be no
 * pages to fail it.
 */
if (linksSeen < 20) {
  failures.push(
    `only ${linksSeen} links were checked across ${pages.length} pages, expected at ` +
      `least 20 — has the markup changed shape, or did the matcher stop matching?`,
  );
}

/**
 * The check that keeps the JSON-LD check honest.
 *
 * The matcher is a regex over built HTML, so a renaming, a change in how Next emits
 * the tag, or the block simply not being rendered would all make it match nothing —
 * and a loop over nothing reports success. One course page carries one block today.
 */
if (jsonLdBlocksSeen < 1) {
  failures.push(
    "no JSON-LD blocks were found in any built page — structured data should be on " +
      "every course page, so either it stopped rendering or this check stopped matching",
  );
}

/**
 * The check that keeps the check above honest.
 *
 * `isPublic` matches by filename, so a rename, a route move or a change to the seeded
 * course would make it match nothing — and a rule that matches nothing reports
 * success. Four is the number of public pages today: the landing page, the catalogue,
 * pricing, and at least one course.
 */
if (publicPagesSeen < 4) {
  failures.push(
    `only ${publicPagesSeen} public pages were checked for a share image, expected at ` +
      `least 4 — has a route moved, or did the seeded catalogue change?`,
  );
}

if (failures.length > 0) {
  console.error("Document structure problems:\n");
  for (const failure of failures) console.error(`  ${failure}`);
  process.exit(1);
}

console.log(`Document structure is sound across ${pages.length} built pages.`);
