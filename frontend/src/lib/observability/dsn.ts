/**
 * Reading a Sentry DSN without depending on the Sentry SDK.
 *
 * This module exists so `next.config.ts` can put Sentry's ingest host into the
 * Content-Security-Policy without importing the vendor SDK into the build
 * configuration. It is pure string handling and has no other purpose.
 *
 * **Derived rather than configured.** The obvious alternative is a second
 * environment variable naming the ingest origin, and the obvious failure of
 * that is the two disagreeing: a DSN pointed at one Sentry region and a CSP
 * allowing another produces a browser SDK that reports nothing, silently, in
 * the one situation where you need it. One variable cannot contradict itself.
 */

/**
 * The origin a browser SDK POSTs events to, or `""` when there is no usable DSN.
 *
 * A DSN looks like `https://<key>@<host>/<project>`, so the origin is just its
 * scheme and host. Returns `""` rather than throwing: an absent DSN is the
 * ordinary state of this repository, and `next.config.ts` runs on every build.
 */
export function ingestOriginFromDsn(dsn: string | undefined): string {
  if (!dsn) return "";

  try {
    const { protocol, host } = new URL(dsn);
    // A DSN is always http(s). Anything else is a pasted secret of some other
    // kind, and putting it in a CSP would widen the policy on a typo.
    if (protocol !== "https:" && protocol !== "http:") return "";
    return `${protocol}//${host}`;
  } catch {
    return "";
  }
}
