import type { NextConfig } from "next";

/**
 * Same-origin routing (ADR-001 section 2.1).
 *
 * The browser must see exactly one origin, because session cookies are only
 * simple when it does. Until the Cloudflare Worker takes over the `/api/*`
 * split before launch, Next.js proxies those requests to Django.
 *
 * The origin is read from a server-only variable, never a NEXT_PUBLIC_ one:
 * rewrites are evaluated on the server, and the internal API hostname has no
 * business being shipped to the browser.
 */
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

/**
 * Content Security Policy, report-only (ADR-022 section 4).
 *
 * Report-only in both tiers, and this is the browser-facing half. CSP fails
 * silently — a wrong directive does not raise, it removes a stylesheet — so
 * enforcing a policy nobody has observed in a real browser is how a login form
 * stops working without anyone being told. M13 collects reports and M13
 * decides when to enforce.
 *
 * `CSP_MEDIA_SRC` and `CSP_REPORT_URI` come from the environment because the
 * CDN hostname and the report endpoint are deployment facts, not source. Both
 * default to nothing: a policy that hardcoded a guessed CDN would be a
 * fabricated infrastructure fact, and the whole point of report-only is that
 * an empty `media-src` shows up as a report rather than a black video player.
 *
 * `unsafe-inline` appears for styles and nowhere else. Next.js injects inline
 * `<style>` for critical CSS during streaming, and there is no nonce plumbed
 * through it here; script-src stays strict, which is the half that matters for
 * injection.
 */
const mediaSrc = process.env.CSP_MEDIA_SRC ?? "";
const reportUri = process.env.CSP_REPORT_URI ?? "";

const csp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self'${mediaSrc ? ` ${mediaSrc}` : ""}`,
  `media-src 'self'${mediaSrc ? ` ${mediaSrc}` : ""}`,
  "frame-ancestors 'none'",
  "form-action 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  ...(reportUri ? [`report-uri ${reportUri}`] : []),
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,

  /**
   * Trailing slashes, to match Django.
   *
   * Next redirects `/about/` to `/about` by default, and Django's
   * `APPEND_SLASH` redirects `/api/v1/schema` back to `/api/v1/schema/`. Left
   * alone the two disagree forever: a request to any API path bounces between
   * a 308 from Next and a 301 from Django and never resolves. Every endpoint
   * in architecture.md 6.2 ends in a slash, so every one of them would have
   * been affected from M2 onwards.
   *
   * Aligning on trailing slashes fixes it in the direction Django already
   * works. The alternative — `skipTrailingSlashRedirect` — stops the loop by
   * removing canonical redirects entirely, which would leave the static
   * marketing surface reachable at two URLs (invariant 15).
   */
  trailingSlash: true,

  /**
   * Emit a self-contained server bundle at `.next/standalone`.
   *
   * The container runtime stage copies that instead of the full
   * `node_modules`, which is the difference between shipping the dependency
   * tree and shipping only what the server actually imports. Harmless when
   * building outside a container — it is extra output nothing has to use.
   */
  output: "standalone",

  /**
   * Pin the Turbopack root to this directory.
   *
   * Turbopack infers the root by walking up looking for a lockfile. In this
   * monorepo that search escapes the repository entirely and can latch onto a
   * stray `package-lock.json` in the developer's home directory, which makes
   * the build depend on machine state outside version control. Setting it
   * explicitly also narrows filesystem watching to files that matter.
   */
  turbopack: {
    root: import.meta.dirname,
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy-Report-Only",
            value: csp,
          },
        ],
      },
    ];
  },

  async rewrites() {
    return {
      beforeFiles: [],

      /**
       * `afterFiles` runs *after* the filesystem is checked, so any Route
       * Handler that genuinely exists under `src/app/api/` takes precedence
       * and everything else falls through to Django.
       *
       * This matters more than it looks. architecture.md section 3.2 describes
       * a BFF where the browser only ever talks to Next.js, while section 4.3
       * describes path routing straight to Django — two different
       * architectures. ADR-001 leaves that open until M2. Ordering the rewrite
       * this way means both remain possible: add a Route Handler and it wins;
       * add nothing and Django serves the route.
       */
      afterFiles: [
        {
          /**
           * `:path(.*)` rather than `:path*`.
           *
           * `:path*` splits the remainder on `/`, so a terminal slash is
           * consumed as a separator and never reaches Django —
           * `/api/v1/schema/` arrives as `/api/v1/schema`, Django's
           * APPEND_SLASH redirects it back, and the request bounces forever.
           * A greedy capture forwards the path verbatim, trailing slash and
           * all.
           */
          source: "/api/:path(.*)",
          destination: `${apiOrigin}/api/:path`,
        },
      ],

      fallback: [],
    };
  },
};

export default nextConfig;
