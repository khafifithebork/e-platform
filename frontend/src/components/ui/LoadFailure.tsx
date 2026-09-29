"use client";

import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

/**
 * A load that failed, with a way out of it.
 *
 * **Four surfaces said "try again" and gave nobody anything to press.**
 * `MyCourses`, `LessonGate`, `AccountDetails` and `LessonPlayer` each ended a
 * failed fetch with advice — "Try again in a moment", "Reloading the page usually
 * fixes it" — and the common cause of all four is a transient network failure, the
 * case where one click fixes it. Dispensing advice instead is a dead end wearing a
 * helpful tone.
 *
 * They also looked like three different things: a bare `<p className="text-danger">`,
 * a page-level interstitial, and two `Notice`s. One component for all four is the
 * consistency half of the same fix.
 *
 * **Retrying re-runs the load, not the page.** A reload throws away everything else
 * on screen — a half-read transcript, a filtered catalogue, an unsent form — to
 * recover one request. Each caller keeps a counter in its effect's dependency array,
 * so pressing this re-runs exactly the fetch that failed.
 *
 * ## What this deliberately does not do
 *
 * **No automatic retry.** A component that retried on its own would hammer an API
 * that is already failing, and the failure a learner sees most is a lapsed
 * connection, where the right number of attempts is "when they are back". Backoff is
 * the answer to a *server* under load, and nothing here is on that path.
 *
 * **No attempt counter and no "still not working" wording.** Saying "that did not
 * work either" on the second press requires tracking something the visitor can see
 * for themselves, and the honest message is the same message.
 *
 * **Not used by `CourseSearch`.** Its failure is inline and tied to the field, and
 * the debounce re-fires on the next keystroke — the retry already exists, and a
 * button beside a box somebody is still typing in is noise.
 */
export function LoadFailure({
  title,
  children,
  onRetry,
  retrying = false,
}: {
  /** Optional heading. Omitted where the surrounding page already has one. */
  title?: string;
  /** What failed, in the caller's own words. */
  children: React.ReactNode;
  onRetry: () => void;
  /** True while the retry is in flight, so the button cannot be pressed twice. */
  retrying?: boolean;
}) {
  return (
    <div className="flex flex-col items-start gap-4">
      <Notice tone="error" title={title}>
        {children}
      </Notice>

      {/*
       * Outside the `Notice`, not inside it. The notice is `role="alert"` with
       * `aria-live="assertive"`, and a live region's job is to announce text —
       * putting a control in one means assistive technology may read the button's
       * label as part of the announcement, and in some combinations re-announce the
       * whole region when the button's own state changes.
       */}
      <Button variant="secondary" size="sm" onClick={onRetry} pending={retrying} pendingLabel="Trying…">
        Try again
      </Button>
    </div>
  );
}
