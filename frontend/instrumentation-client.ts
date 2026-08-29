/**
 * Next's browser instrumentation hook, loaded before the app renders.
 *
 * Thin on purpose — see `instrumentation.ts` and ADR-027 §1. This runs on
 * every page including the statically generated marketing surface, so it must
 * stay cheap and must not fetch anything: invariant 15 is about request-time
 * API calls, and an error reporter that made one would be the first exception.
 */

import { initialiseBrowserErrorReporting } from "@/lib/observability/sentry";

initialiseBrowserErrorReporting();
