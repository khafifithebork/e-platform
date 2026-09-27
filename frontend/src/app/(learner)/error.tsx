"use client";

import Link from "next/link";
import { useEffect } from "react";

import { Button, buttonStyles } from "@/components/ui/Button";
import { PageTitle } from "@/components/ui/PageTitle";
import { reportBoundaryError } from "@/lib/observability/sentry";

/**
 * When a learner page throws during render.
 *
 * ADR-031 §2. This covers `/my-courses` and the lesson route — both
 * authenticated, both client components almost entirely (ADR-026 decision 2),
 * and one of them the only dynamic route in the product. Before this existed a
 * render error here produced Next's built-in page: unstyled, no shell, no
 * navigation, no skip link, and no way out but the browser's own controls.
 *
 * **The worst-placed learner is the one who was mid-lesson.** `LessonPlayer`
 * reports progress on an interval and a final beat on unmount; a render error
 * takes the component down, and whatever that beat had not yet sent is gone. So
 * this says so. A page implying everything is fine would be worse than one
 * admitting it does not know.
 *
 * **What it must not do is show the error.** `error.message` can carry a URL, an
 * id, or a fragment of a response — `lib/observability/redact.ts` exists because
 * ADR-027 took that seriously on the *reporting* path, and the visible page must
 * not undo it. The digest goes to Sentry, not to the DOM.
 */
export default function LearnerError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // In an effect, not the render body: React may render a boundary twice and
    // a report in the body would then send the same event twice.
    reportBoundaryError(error);
  }, [error]);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-6 py-16">
      <PageTitle variant="interstitial">Something went wrong</PageTitle>

      <p className="text-ink-muted">
        This page stopped working. If you were part-way through a lesson, the
        last few seconds of your progress may not have been saved.
      </p>

      <div className="flex flex-col gap-3 sm:flex-row">
        {/*
         * `reset()` re-renders the segment without a full navigation, which is
         * right here because the common cause is a failed request rather than a
         * broken build. No retry counter and no backoff: a person pressing a
         * button twice is not a retry storm.
         */}
        <Button onClick={reset}>Try again</Button>

        {/* `buttonStyles`, not a hand-written class string: a link is not a
            `<button>`, so it takes the styles rather than the component
            (`docs/design-system.md` §4). Hand-rolling one here is how the
            landing page's two calls to action ended up 2px apart. */}
        <Link href="/my-courses" className={buttonStyles({ variant: "secondary" })}>
          Go to my courses
        </Link>
      </div>
    </div>
  );
}
