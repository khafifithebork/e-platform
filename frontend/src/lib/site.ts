/**
 * The site's own public origin, and what happens when nobody has set one.
 *
 * Canonical URLs, `sitemap.ts`, `robots.ts` and Open Graph all need an absolute
 * origin, and **this repository has never configured one** — no domain has been
 * chosen (ADR-025 picked the hosting, not the name). So the interesting question
 * is not how to read the variable, it is what to do when it is missing.
 *
 * **Missing means "do not claim anything", not "guess".** Unset gives no
 * canonical tag, an empty sitemap and `Disallow: /`. The alternative — defaulting
 * to `http://localhost:3000` — is worse than being unindexed and it is silent: a
 * deploy that forgot the variable would publish canonical tags telling every
 * crawler that the real address of each page is a machine it cannot reach, which
 * de-indexes the pages *and* looks like it worked.
 *
 * **A malformed value is loud, though.** `SITE_URL=lingua.example` with no scheme
 * throws and stops the build. A typo is not the same situation as an absence: the
 * absence is the current, expected state, and the typo is somebody trying to
 * configure this and getting it wrong, which they need to be told about.
 *
 * Server-only, not `NEXT_PUBLIC_`. Every consumer runs during the build or on the
 * server, and `.env.example` asks for the prefix only where the browser genuinely
 * needs the value. That the origin ends up visible *in* the HTML is not a reason
 * to ship it *to* the bundle.
 */

import type { Metadata } from "next";

/** Thrown for a value that is set but unusable, to stop a build rather than ship. */
export class InvalidSiteUrl extends Error {
  constructor(value: string, detail: string) {
    super(
      `SITE_URL is set to ${JSON.stringify(value)}, which is not a usable origin: ${detail}\n` +
        `Expected an absolute http(s) URL, for example https://lingua.example. ` +
        `Leave it unset to publish no canonical URLs and an empty sitemap.`,
    );
    this.name = "InvalidSiteUrl";
  }
}

/**
 * The configured origin, or `null` when there is none.
 *
 * Returns the origin only — scheme, host, port — so a value with a path, a query
 * or a trailing slash cannot produce `https://x.example//courses/`. Read on every
 * call rather than cached at module load, because a test needs to change it.
 */
export function siteUrl(): URL | null {
  const raw = process.env.SITE_URL?.trim();
  if (!raw) return null;

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new InvalidSiteUrl(raw, "it does not parse as a URL");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new InvalidSiteUrl(raw, `the scheme is ${parsed.protocol} rather than http or https`);
  }

  return new URL(parsed.origin);
}

/**
 * Whether this origin should be in a search index at all.
 *
 * A local or private origin is a real, working configuration — somebody
 * previewing a production build — and it is never a site a crawler should see.
 * Separating this from `siteUrl()` keeps "can I build a URL" apart from "should I
 * invite indexing", which are different questions with different answers.
 */
export function isIndexable(url: URL | null): boolean {
  if (url === null) return false;

  const host = url.hostname;
  return !(
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "[::1]" ||
    host === "::1" ||
    host.endsWith(".localhost") ||
    host.endsWith(".test") ||
    host.endsWith(".local")
  );
}

/**
 * Every statically generated public path, in canonical form.
 *
 * **Trailing slashes, because `next.config.ts` sets `trailingSlash: true`.** A
 * sitemap listing `/courses` against a site that serves `/courses/` advertises a
 * URL that answers 308, so every entry costs a crawler a redirect and the
 * canonical it eventually reads disagrees with the one it was given. The root is
 * `/` either way.
 *
 * Course paths are appended by `sitemap.ts` from the same build-time catalogue
 * read the pages use, so a course cannot be in one and missing from the other.
 */
export const PUBLIC_PATHS = ["/", "/courses/", "/pricing/"] as const;

/** A canonical absolute URL for a path, or `null` when there is no origin. */
export function canonical(path: string): string | null {
  const origin = siteUrl();
  if (origin === null) return null;

  return new URL(path, origin).toString();
}

/**
 * The metadata a public page declares: its canonical URL and its link preview.
 *
 * **One helper rather than the same four fields written out on each page**, for a
 * reason beyond repetition. Next inherits metadata, and the fields here are the
 * ones where inheritance is actively wrong: an `alternates.canonical` or an
 * `openGraph.url` set anywhere a non-public route can inherit it claims that two
 * different pages are the same page. Keeping them in a function that takes the path
 * makes "which pages have a canonical" a list you can read, and `seo.test.ts` reads
 * exactly that list.
 *
 * `path` is the canonical form, with the trailing slash `next.config.ts` serves.
 *
 * ## It no longer sets `openGraph` or `twitter`, and that is a correction
 *
 * **It did, and doing so silently stripped three tags from every public page.**
 * Next merges metadata *shallowly*: a page that sets `openGraph` **replaces** the
 * parent's whole object rather than merging into it — the documentation's own words
 * are that "duplicate keys are replaced based on their ordering". So setting
 * `openGraph: { title, description, url }` here discarded the root layout's
 * `og:site_name` and `og:locale`, and from 2026-09-30 it would also have discarded
 * the `og:image` that `opengraph-image.tsx` contributes.
 *
 * Found by comparing built HTML: `/login`, which sets no `openGraph` at all, carried
 * `og:site_name`, `og:locale` and `og:image`. `/`, which used this helper, carried
 * none of the three. The tests written with this helper asserted the fields it set
 * and could not see the ones it removed.
 *
 * **So it sets none of them, and everything is inherited.** Next derives `og:title`
 * from the resolved title and `og:description` from the resolved description when
 * `openGraph` does not name them, which is where those two now come from.
 *
 * What that costs, stated rather than discovered: **`og:url` is no longer emitted**,
 * and `og:title` is now the *templated* title — "Courses · Lingua" rather than
 * "Courses". Both are acceptable. `og:url` duplicates the `<link rel="canonical">`
 * this helper still sets, which is what crawlers use; and the site name appearing
 * twice on a share card is a smaller fault than the card having no image.
 *
 * `scripts/assert-page-structure.mjs` now asserts `og:image` on every built public
 * page, because this was invisible to every test that existed.
 *
 * **The URLs are absolute, and that is not a style choice.** Next's documentation
 * is explicit: *"Using a relative path in a URL-based metadata field without
 * configuring a metadataBase will cause a build error."* Since the unset origin is
 * the current and expected state, a relative `canonical` would break every build
 * this repository does today — the exact opposite of failing safe. So the fields
 * are built absolutely when there is an origin and **left out entirely** when there
 * is not, rather than delegating the question to Next.
 */
export function publicMetadata({
  title,
  description,
  path,
  absoluteTitle = false,
}: {
  title: string;
  /** Omitted when the source has none — a course with an empty description. */
  description?: string;
  path: (typeof PUBLIC_PATHS)[number] | `/courses/${string}/`;
  /**
   * For the landing page only.
   *
   * The root layout sets `title.template: "%s · Lingua"`, which a page's plain
   * `title` string is composed into. The landing page's title *is* "Lingua", so
   * composing it gives "Lingua · Lingua"; `title.absolute` opts out of the
   * template, which is what the documented behaviour is for.
   */
  absoluteTitle?: boolean;
}): Metadata {
  const url = canonical(path);

  return {
    // Spread rather than `x: value ?? undefined`, so absent keys are genuinely
    // absent. Next treats absent and `undefined` the same; a test reading the
    // exported object does not, and `seo.test.ts` reads it.
    title: absoluteTitle ? { absolute: title } : title,
    ...(description ? { description } : {}),
    ...(url === null ? {} : { alternates: { canonical: url } }),
  };
}
