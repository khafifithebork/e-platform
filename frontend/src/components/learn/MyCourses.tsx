"use client";

import Link from "next/link";
import { BookOpen, Check } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, buttonStyles } from "@/components/ui/Button";
import { LoadFailure } from "@/components/ui/LoadFailure";
import { Notice } from "@/components/ui/Notice";
import { ApiError, api, cursorFrom, type Enrollment } from "@/lib/api/client";
import { resumePoint } from "@/lib/learn/resume";

/**
 * What a learner has started, and where to pick it up.
 *
 * `GET /me/courses/` has existed since M7 and has never had a caller. The
 * endpoint already computes everything shown here — including `next_lesson`,
 * which walks back to the earliest *unfinished* lesson rather than following
 * the bookmark, so a learner who skipped ahead is not quietly written off.
 *
 * **Resume points at `next_lesson`, not `last_lesson`.** They differ for
 * anybody who skipped, and the selector's own comment says which is which: the
 * bookmark is where they were, the next lesson is where they should go.
 */
type State =
  | { status: "loading" }
  /**
   * `cursor` is the next page, or `null` when this is the last one.
   *
   * Held as a cursor rather than the API's `next` URL on purpose: Django builds
   * that URL from the Host header, which the Next.js rewrite sets to its own
   * destination, so it names the internal host and not the origin the browser is
   * on. `cursorFrom` discards it.
   */
  | {
      status: "ready";
      enrollments: Enrollment[];
      cursor: string | null;
      loadingMore: boolean;
      moreFailed: boolean;
    }
  | { status: "anonymous" }
  | { status: "failed" };

export function MyCourses() {
  const [state, setState] = useState<State>({ status: "loading" });
  /**
   * Bumped to retry a failed load.
   *
   * A counter in the effect's dependency array, rather than a reload: a reload
   * throws away everything else on the page to recover one request. See
   * `LoadFailure`.
   */
  const [attempt, setAttempt] = useState(0);

  /**
   * Re-run the load that failed.
   *
   * The reset lives here rather than at the top of the effect, which is where it
   * was first written — `react-hooks/set-state-in-effect` objected, correctly: an
   * unconditional `setState` in an effect body costs an extra render on *every*
   * mount to serve a case that happens rarely. An event handler is where a state
   * reset belongs.
   */
  function retry() {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  useEffect(() => {
    let current = true;

    api
      .myCourses()
      .then((page) => {
        if (current) {
          setState({
            status: "ready",
            enrollments: page.results,
            cursor: cursorFrom(page.next),
            loadingMore: false,
            moreFailed: false,
          });
        }
      })
      .catch((error: unknown) => {
        if (!current) return;

        // A 403 is not a failure here either — it is somebody who is not
        // signed in reaching a page that needs an account. Showing "something
        // went wrong" would send them looking for an outage.
        if (error instanceof ApiError && error.isNotAuthenticated) {
          setState({ status: "anonymous" });
          return;
        }
        setState({ status: "failed" });
      });

    return () => {
      current = false;
    };
  }, [attempt]);

  /**
   * Append the next page.
   *
   * **A failed "load more" must not destroy what is already on screen.** The
   * learner can see their first page; replacing it with an error because the
   * second request failed would lose information they already had. So this sets
   * `moreFailed` alongside the existing list rather than moving to `failed`.
   */
  async function loadMore() {
    if (state.status !== "ready" || state.cursor === null || state.loadingMore) return;

    const { enrollments, cursor } = state;
    setState({ ...state, loadingMore: true, moreFailed: false });

    try {
      const page = await api.myCourses(cursor);
      setState({
        status: "ready",
        enrollments: [...enrollments, ...page.results],
        cursor: cursorFrom(page.next),
        loadingMore: false,
        moreFailed: false,
      });
    } catch {
      // The cursor is kept, so the button stays and a retry is one click away.
      setState({
        status: "ready",
        enrollments,
        cursor,
        loadingMore: false,
        moreFailed: true,
      });
    }
  }

  if (state.status === "loading") {
    return (
      <p aria-live="polite" className="border-y border-line py-12 text-ink-muted">
        Loading your courses…
      </p>
    );
  }

  if (state.status === "anonymous") {
    return (
      <section className="flex flex-col items-start gap-5 border-y border-line py-12 sm:py-16" aria-labelledby="courses-sign-in">
        <BookOpen aria-hidden="true" size={36} strokeWidth={1.5} />
        <div className="flex max-w-lg flex-col gap-3">
          <h2 id="courses-sign-in" className="font-display text-2xl leading-snug text-ink">Your courses, in one place</h2>
          <p className="leading-relaxed text-ink-muted">Sign in to see the courses you have started.</p>
        </div>
        <Link href="/login" className={buttonStyles()}>
          Sign in
        </Link>
      </section>
    );
  }

  if (state.status === "failed") {
    // `LoadFailure` rather than the bare red paragraph this used to be: the same
    // treatment as every other failed load in the app, and with something to press.
    return (
      <LoadFailure onRetry={retry}>
        Your courses could not be loaded.
      </LoadFailure>
    );
  }

  if (state.enrollments.length === 0) {
    // Not an error, and not an empty list either. Somebody enrols by starting
    // a lesson — there is no enrol button — so the useful thing to offer is
    // the catalogue.
    return (
      <section className="flex flex-col items-start gap-5 border-y border-line py-12 sm:py-16" aria-labelledby="courses-empty">
        <BookOpen aria-hidden="true" size={36} strokeWidth={1.5} />
        <div className="flex max-w-lg flex-col gap-3">
          <h2 id="courses-empty" className="font-display text-2xl leading-snug text-ink">Your next course starts here</h2>
          <p className="leading-relaxed text-ink-muted">
            You have not started a course yet. Starting a lesson is what enrols
            you — there is nothing else to sign up for.
          </p>
        </div>
        <Link href="/courses" className={buttonStyles()}>
          Browse the catalogue
        </Link>
      </section>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <ul aria-label="Your courses" className="flex flex-col border-t border-line">
        {state.enrollments.map((enrollment) => (
          <li key={enrollment.id}>
            <EnrollmentCard enrollment={enrollment} />
          </li>
        ))}
      </ul>

      {state.moreFailed && (
        <Notice tone="error">
          The rest of your courses could not be loaded. Your place is not lost —
          try again.
        </Notice>
      )}

      {/*
       * A button, not page numbers. A learner's own course list is a short list
       * they scan, not a table they navigate — and cursor pagination gives no
       * total, so numbered pages could not even say how many there are.
       *
       * Rendered only when the API said there is another page. Absent on a
       * single-page response, which is the common case.
       */}
      {state.cursor !== null && (
        <Button
          variant="secondary"
          onClick={loadMore}
          pending={state.loadingMore}
          pendingLabel="Loading…"
          className="self-start"
        >
          Show more courses
        </Button>
      )}
    </div>
  );
}

function EnrollmentCard({ enrollment }: { enrollment: Enrollment }) {
  const done = enrollment.completed_lesson_count;
  const total = enrollment.lesson_count;
  const resume = resumePoint(enrollment);

  return (
    <article
      aria-labelledby={`enrollment-${enrollment.id}`}
      className="flex min-w-0 flex-col gap-6 border-b border-line py-8 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <h2 id={`enrollment-${enrollment.id}`} className="break-words font-display text-2xl leading-snug text-ink [overflow-wrap:anywhere]">
          <Link href={`/courses/${enrollment.course_slug}`} className="hover:text-accent">
            {enrollment.course_title}
          </Link>
        </h2>

        {/*
         * A native progress element, not a styled div.
         *
         * It comes with the right role and value semantics, so a screen reader
         * announces "3 of 8" without any ARIA — and the visible text says the
         * same thing rather than leaving the bar as the only source.
         */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <progress
            value={done}
            max={total}
            aria-label={`Progress through ${enrollment.course_title}`}
            className="course-progress h-2 w-full max-w-56 min-w-0"
          />
          <span className="text-sm tabular-nums text-ink-muted">
            {done} of {total} lessons
          </span>
        </div>
      </div>

      {resume.status === "finished" ? (
        <p className="flex items-center gap-2 text-sm font-medium text-success"><Check aria-hidden="true" size={18} />Finished</p>
      ) : (
        <Link
          href={resume.href}
          className={buttonStyles({ className: "w-full shrink-0 self-start sm:w-auto sm:self-center" })}
        >
          {/* Short wording, because this sits in a course row.
              `CourseProgress` says the same thing at length in a one-line
              strip; `resumePoint` owns the rule, each caller owns its voice. */}
          {resume.started ? "Continue" : "Start"}
        </Link>
      )}
    </article>
  );
}
