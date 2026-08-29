"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, type Enrollment } from "@/lib/api/client";

/**
 * Where this learner got to in this course, on a page that cannot know.
 *
 * **The course page is statically generated** (invariant 15) — one HTML file
 * served to everyone, built before any of these learners existed. So progress
 * cannot be baked in, and this resolves it after hydration, the same shape
 * `AuthMenu` uses and for the same reason.
 *
 * **Renders nothing at all in three of its four states**: while resolving,
 * for a visitor with no account, and for somebody who has not started this
 * course. That is deliberate — this is a strip of personal detail on an
 * otherwise impersonal page, and an empty "0 of 8 lessons" for every anonymous
 * visitor would be noise attached to a fact they cannot act on.
 *
 * It reads `/me/courses/` rather than anything course-specific: no endpoint
 * returns one enrolment by course, the list is a learner's own handful, and
 * inventing an endpoint to save a filter is not this milestone's business.
 */
export function CourseProgress({ courseSlug }: { courseSlug: string }) {
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);

  useEffect(() => {
    let current = true;

    api
      .myCourses()
      .then((page) => {
        if (!current) return;
        setEnrollment(page.results.find((row) => row.course_slug === courseSlug) ?? null);
      })
      .catch(() => {
        // Anonymous visitors get a 403 here, which is the common case on a
        // public page and not a fault. Anything else — an outage — also lands
        // here and also shows nothing: this is supplementary detail, and it
        // must never be the reason a course page looks broken.
        if (current) setEnrollment(null);
      });

    return () => {
      current = false;
    };
  }, [courseSlug]);

  if (!enrollment) return null;

  const finished = enrollment.next_lesson_slug === null;

  return (
    <aside
      aria-label="Your progress"
      className="flex flex-wrap items-center gap-4 rounded-[--radius-md]
        border border-line bg-surface-sunken px-4 py-3"
    >
      <progress
        value={enrollment.completed_lesson_count}
        max={enrollment.lesson_count}
        aria-label="Lessons completed"
        className="h-1.5 w-32"
      />
      <span className="text-sm text-ink-muted">
        {enrollment.completed_lesson_count} of {enrollment.lesson_count} lessons
      </span>

      {finished ? (
        <span className="text-sm font-medium text-success">Finished</span>
      ) : (
        <Link
          href={`/courses/${courseSlug}/lessons/${enrollment.next_lesson_slug}`}
          className="text-sm text-accent hover:text-accent-hover"
        >
          {/*
           * The same distinction "my courses" makes: a course with an enrolment
           * but no bookmark was started and abandoned before the first lesson,
           * and "continue" would be describing something that did not happen.
           */}
          {enrollment.last_lesson_slug ? "Continue where you left off" : "Start the first lesson"}
        </Link>
      )}
    </aside>
  );
}
