"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StaggerItem, StaggerList } from "@/components/motion/StaggerList";
import { Button, buttonStyles } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
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
      <p aria-live="polite" className="text-ink-muted">
        Loading your courses…
      </p>
    );
  }

  if (state.status === "anonymous") {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-ink-muted">Sign in to see the courses you have started.</p>
        <Link href="/login" className="text-accent hover:text-accent-hover">
          Sign in
        </Link>
      </div>
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
      <div className="flex flex-col gap-4">
        <p className="text-ink-muted">
          You have not started a course yet. Starting a lesson is what enrols
          you — there is nothing else to sign up for.
        </p>
        <Link href="/courses" className="text-accent hover:text-accent-hover">
          Browse the catalogue
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <StaggerList className="flex flex-col gap-4">
        {state.enrollments.map((enrollment) => (
          <StaggerItem key={enrollment.id}>
            <EnrollmentCard enrollment={enrollment} />
          </StaggerItem>
        ))}
      </StaggerList>

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
    <Card
      as="article"
      aria-labelledby={`enrollment-${enrollment.id}`}
      hoverable
      className="flex flex-col gap-3"
    >
      <h2 id={`enrollment-${enrollment.id}`} className="font-display text-xl text-ink">
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
      <div className="flex items-center gap-3">
        <progress
          value={done}
          max={total}
          aria-label={`Progress through ${enrollment.course_title}`}
          className="h-1.5 w-40"
        />
        <span className="text-sm text-ink-muted">
          {done} of {total} lessons
        </span>
      </div>

      {resume.status === "finished" ? (
        <p className="text-sm text-success">Finished</p>
      ) : (
        <Link
          href={resume.href}
          // `sm`, not `lg`: this sits inside a card in a list, not at the top of
          // a page. It was `px-4 py-2` with no minimum height and came out 36px
          // tall — below the 44px target the primitive has always set, which is
          // what opting out of the primitive costs.
          className={buttonStyles({ size: "sm", lift: true, className: "self-start" })}
        >
          {/* Short wording, because this sits on a card in a list.
              `CourseProgress` says the same thing at length in a one-line
              strip; `resumePoint` owns the rule, each caller owns its voice. */}
          {resume.started ? "Continue" : "Start"}
        </Link>
      )}
    </Card>
  );
}
