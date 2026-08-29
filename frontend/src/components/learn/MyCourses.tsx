"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, api, type Enrollment } from "@/lib/api/client";

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
  | { status: "ready"; enrollments: Enrollment[] }
  | { status: "anonymous" }
  | { status: "failed" };

export function MyCourses() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let current = true;

    api
      .myCourses()
      .then((page) => {
        if (current) setState({ status: "ready", enrollments: page.results });
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
  }, []);

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
    return (
      <p className="text-danger">
        Your courses could not be loaded. Try again in a moment.
      </p>
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
    <ul className="flex flex-col gap-4">
      {state.enrollments.map((enrollment) => (
        <li key={enrollment.id}>
          <EnrollmentCard enrollment={enrollment} />
        </li>
      ))}
    </ul>
  );
}

function EnrollmentCard({ enrollment }: { enrollment: Enrollment }) {
  const done = enrollment.completed_lesson_count;
  const total = enrollment.lesson_count;
  const finished = enrollment.next_lesson_slug === null;

  return (
    <article
      aria-labelledby={`enrollment-${enrollment.id}`}
      className="flex flex-col gap-3 rounded-[--radius-lg] border border-line bg-surface p-5"
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

      {finished ? (
        // `next_lesson` is null when nothing is left. Offering "resume" here
        // would send somebody back into a course they have finished.
        <p className="text-sm text-success">Finished</p>
      ) : (
        <Link
          href={`/courses/${enrollment.course_slug}/lessons/${enrollment.next_lesson_slug}`}
          className="self-start rounded-[--radius-md] bg-accent px-4 py-2 text-sm
            font-medium text-on-accent transition-colors hover:bg-accent-hover"
        >
          {/*
           * "Continue" only once something has been watched. A course with an
           * enrolment but no bookmark was started and abandoned before the
           * first lesson, and "continue" would be describing something that
           * did not happen.
           */}
          {enrollment.last_lesson_slug ? "Continue" : "Start"}
        </Link>
      )}
    </article>
  );
}
