/**
 * Next's server-side instrumentation hook.
 *
 * Thin on purpose: everything about *what* is reported lives in
 * `src/lib/observability/sentry.ts`, which is the only module allowed to
 * import the vendor SDK. See ADR-027 §1.
 *
 * `register` is called once per server instance and completes before the
 * server handles requests, so an error thrown by the first request is already
 * covered. `onRequestError` is Next's hook for errors raised inside Server
 * Components, route handlers and server actions — the ones that never reach
 * the browser and would otherwise be visible only in a log line.
 *
 * ---
 *
 * **This file does not run on the deployment target, and that is measured.**
 *
 * Under `next dev` and `next start` it works: Next compiles it to
 * `.next/server/instrumentation.js` and the Sentry SDK lands in the server
 * chunks. Under OpenNext on Cloudflare Workers it does not — no JavaScript in
 * `.open-next/server-functions/` references `@sentry`, and adding the whole
 * server SDK moved the Worker by 0.12 KiB gzipped, which is the size of
 * nothing. `withSentryConfig` was tried as the missing piece and did not
 * change it. ADR-027 §4 has the evidence and what is still open.
 *
 * It is kept rather than deleted because it is correct, it is the documented
 * Next integration, it works in development where it is doing its job today,
 * and it starts working the moment the frontend runs on Node. What it is not
 * is a control that covers production, and that is written here rather than
 * assumed by whoever reads this next.
 */

import { initialiseServerErrorReporting } from "@/lib/observability/sentry";

export { onRequestError } from "@/lib/observability/sentry";

export function register(): void {
  initialiseServerErrorReporting();
}
