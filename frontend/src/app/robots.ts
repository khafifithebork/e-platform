import type { MetadataRoute } from "next";

import { isIndexable, siteUrl } from "@/lib/site";

/**
 * Paths that must never be in a search index.
 *
 * Not a security control — `_headers`, the session cookie and every server-side
 * permission check are what protect these, and a crawler that ignores this file
 * still gets refused. This is about not advertising them: a sign-in form in search
 * results is a phishing lure with our name on it, and an indexed
 * `/reset-password/` invites people to arrive there without a token.
 *
 * `/api/` is listed because the Next rewrite serves Django under the site's own
 * origin, so from a crawler's point of view the API is part of this site.
 */
const NEVER_INDEX = [
  "/login/",
  "/register/",
  "/forgot-password/",
  "/reset-password/",
  "/verify-email/",
  "/my-courses/",
  // Added with the route itself, 2026-09-29. An account page is the most
  // personal surface in the product and the least useful thing in a search index.
  "/account/",
  "/api/",
] as const;

/**
 * `robots.txt`, generated at build time.
 *
 * **Refuses everything unless there is a real, public origin.** With no
 * `SITE_URL`, or one pointing at localhost, this emits `Disallow: /` — the
 * fail-safe chosen with the owner on 2026-09-28. A preview build and a forgotten
 * environment variable then both behave the same way: nothing gets indexed, which
 * is recoverable, rather than the wrong URLs getting indexed, which is not.
 *
 * `isIndexable` is separate from `siteUrl` because a localhost origin is a
 * perfectly valid configuration for building URLs and never a site to invite
 * crawlers to — see `src/lib/site.ts`.
 */
export default function robots(): MetadataRoute.Robots {
  const origin = siteUrl();

  // `origin === null` first so TypeScript narrows it for the lines below;
  // `isIndexable` handles null too, but a predicate cannot narrow its argument.
  if (origin === null || !isIndexable(origin)) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }

  return {
    rules: { userAgent: "*", allow: "/", disallow: [...NEVER_INDEX] },
    sitemap: new URL("/sitemap.xml", origin).toString(),
    host: origin.host,
  };
}
