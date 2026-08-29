/**
 * The only module in `frontend/` that imports the Sentry SDK.
 *
 * The backend keeps the vendor behind one import for invariant 4's sake
 * (ADR-027 §1) and this mirrors it, for a reason of its own: Next loads
 * `instrumentation.ts` and `instrumentation-client.ts` by convention, in
 * different runtimes, and the tempting shape is a `Sentry.init` in each. Two
 * initialisations drift, and the half that drifts is the browser — where the
 * options that matter are the privacy ones.
 *
 * So the entry points stay thin and this file decides what is sent.
 * `observability.test.ts` fails if a second module imports the SDK.
 *
 * **Nothing here has ever reported an event.** No DSN exists in this
 * repository. ADR-027 §3.
 */

import * as Sentry from "@sentry/nextjs";

import { redactAddresses } from "./redact";

/**
 * Integrations we refuse, matched by name prefix.
 *
 * Session Replay records the DOM, and this application's authenticated pages
 * carry a learner's name, their course list and their progress. Recording that
 * to a third party is a different decision from reporting an error, and it is
 * not one M14 T5 is making.
 *
 * A filter rather than simply not adding them: they are opt-in today, and this
 * is what keeps that true if a future SDK version changes its defaults.
 */
const REFUSED = ["Replay", "Feedback"];

/**
 * Typed structurally rather than as `Integration`, which `@sentry/nextjs` does
 * not re-export. All this needs is a name, and saying so keeps it working
 * across SDK versions that move the type around.
 */
function permitted<T extends { name: string }>(integrations: T[]): T[] {
  return integrations.filter(
    (integration) => !REFUSED.some((name) => integration.name.startsWith(name)),
  );
}

function shared() {
  return {
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "local",
    // No user object, no IP address, no headers. Explicit rather than relying
    // on the default staying this way.
    sendDefaultPii: false,
    // Tracing bills a quota separate from errors and the free tier's is small.
    // Whether we want it at all is M14 T6's question.
    tracesSampleRate: 0,
    integrations: permitted,
    beforeSend: (event: Sentry.ErrorEvent) => redactAddresses(event),
  };
}

/**
 * Browser. `NEXT_PUBLIC_` because it must reach the bundle — a browser DSN is
 * public by design; it is a write-only ingest key, not a credential that can
 * read anything back.
 *
 * **Baked in at build time**, like `API_ORIGIN` before it (M15 spec §4.3), so
 * one build cannot serve two environments. That is the same argument §11 #4
 * turns on and another reason to answer it.
 */
export function initialiseBrowserErrorReporting(): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({ dsn, ...shared() });
}

/**
 * Server — the Next server running inside the Cloudflare Worker.
 *
 * Sentry requires the `nodejs_compat` flag and a compatibility date of
 * 2025-08-16 or later for `https.request`. `wrangler.jsonc` already satisfies
 * both, which was checked before this was written rather than after it failed.
 */
export function initialiseServerErrorReporting(): void {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({ dsn, ...shared() });
}

/**
 * Next calls this for errors thrown in Server Components and route handlers.
 * Re-exported so the entry point does not have to import the SDK.
 */
export const onRequestError = Sentry.captureRequestError;
