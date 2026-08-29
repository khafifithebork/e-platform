/**
 * Removing email addresses from anything on its way to Sentry.
 *
 * The twin of `apps/core/observability.py`'s scrubber, and deliberately so.
 * The browser is where a learner types their own address, so an error thrown
 * while validating a sign-in form is the most likely place for one to escape —
 * and `sendDefaultPii: false` does not help, because that governs what the SDK
 * attaches, not what our own error messages say.
 *
 * Duplicated across two languages rather than shared, because the alternative
 * is shipping a scrubbing service both tiers call at the moment they are
 * trying to report that something is broken.
 */

const REDACTED = "[redacted]";

// Matched to the backend's pattern so the two tiers redact the same things.
// Loose on the local part, strict on the shape: over-redacting costs a less
// readable stack trace, under-redacting puts a learner's address in a
// third-party dashboard nobody audits.
const EMAIL = /[^\s<>@,;:"'()[\]]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}/g;

// A Sentry event is a tree and this walks it. The cap is not about cycles —
// an event is JSON-serialisable by the time it gets here — but about never
// throwing inside `beforeSend`, which drops the event entirely.
const MAX_DEPTH = 10;

export function redactAddresses<T>(value: T, depth = 0): T {
  if (depth > MAX_DEPTH) return value;

  if (typeof value === "string") {
    return value.replace(EMAIL, REDACTED) as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactAddresses(item, depth + 1)) as T;
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        redactAddresses(item, depth + 1),
      ]),
    ) as T;
  }
  return value;
}

export { REDACTED };
