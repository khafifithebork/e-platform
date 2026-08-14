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

const nextConfig: NextConfig = {
  reactStrictMode: true,

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
          source: "/api/:path*",
          destination: `${apiOrigin}/api/:path*`,
        },
      ],

      fallback: [],
    };
  },
};

export default nextConfig;
