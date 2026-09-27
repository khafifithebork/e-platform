/**
 * The resume rule, tested once now that it is written once.
 *
 * **Not a coverage hole being filled — the opposite.** Both components that used
 * to own a copy of this rule already tested it, and both tested it properly:
 * `MyCourses.test.tsx` has "points at the next lesson, not the bookmark" with the
 * skipper's reasoning written out, and `CourseProgress.test.tsx` uses a fixture
 * whose bookmark and next lesson deliberately differ. Provoking this file's
 * extraction by making `resumePoint` follow the bookmark fails five tests, three
 * of which are theirs.
 *
 * So the duplication was two copies of the rule *and* two copies of its tests.
 * This file is what lets the component tests go back to being about rendering —
 * a label, a href, a "Finished" — while the rule they both depend on has one
 * home and one set of assertions.
 *
 * The skipper case lives here because it is the case that separates a correct
 * implementation from a plausible one, and it belongs with the rule rather than
 * in two components that merely consume it.
 */

import { describe, expect, it } from "vitest";

import type { Enrollment } from "@/lib/api/client";
import { resumePoint } from "@/lib/learn/resume";

function enrollment(over: Partial<Enrollment> = {}): Enrollment {
  return {
    id: "e1",
    course_slug: "beginner-spanish",
    course_title: "Beginner Spanish",
    last_lesson: null,
    last_lesson_slug: null,
    next_lesson: "l1",
    next_lesson_slug: "greetings",
    completed_lesson_count: 0,
    lesson_count: 8,
    last_activity: null,
    started_at: "2026-09-01T00:00:00Z",
    completed_at: null,
    ...over,
  } as Enrollment;
}

describe("a course with lessons left", () => {
  it("points at the next lesson", () => {
    expect(resumePoint(enrollment())).toEqual({
      status: "resume",
      href: "/courses/beginner-spanish/lessons/greetings",
      started: false,
    });
  });

  it("is not 'started' until something has been watched", () => {
    // Enrolment happens by opening a lesson, so enrolled-and-never-watched is a
    // real state. "Continue" would describe something that did not happen.
    expect(resumePoint(enrollment())).toMatchObject({ started: false });
    expect(resumePoint(enrollment({ last_lesson_slug: "greetings" }))).toMatchObject({
      started: true,
    });
  });

  it("follows the next lesson and not the bookmark, for somebody who skipped ahead", () => {
    /**
     * **The case that separates a correct implementation from a plausible one.**
     *
     * This learner's bookmark is on lesson 5 and their earliest unfinished
     * lesson is 2 — they jumped forward. The API's selector walks back to 2
     * deliberately so they are not written off; a client that resumed from the
     * bookmark would undo that and skip the lesson they still owe.
     *
     * A fixture where the two fields agree cannot see the difference, which is
     * why both components' versions of this test set them apart on purpose.
     */
    const skipper = enrollment({
      last_lesson_slug: "lesson-5",
      next_lesson_slug: "lesson-2",
      completed_lesson_count: 1,
    });

    expect(resumePoint(skipper)).toEqual({
      status: "resume",
      href: "/courses/beginner-spanish/lessons/lesson-2",
      started: true,
    });
  });
});

describe("a finished course", () => {
  it("is finished when there is no next lesson, whatever the counts say", () => {
    /**
     * Keyed on `next_lesson_slug`, not on `completed_lesson_count === lesson_count`.
     * The counts are a display detail and can lag or disagree — a lesson added
     * to a published course moves `lesson_count` without touching anyone's
     * progress — while the absence of a next lesson is the server's own answer.
     */
    const done = enrollment({
      last_lesson_slug: "lesson-8",
      next_lesson_slug: null,
      completed_lesson_count: 8,
    });

    expect(resumePoint(done)).toEqual({ status: "finished" });
  });

  it("stays finished even if the counts look unfinished", () => {
    // The twin for the reasoning above: a course whose lesson count grew is
    // still finished as far as the server is concerned, and this must not
    // invent a resume link with `next_lesson_slug: null` in the URL.
    const countsDisagree = enrollment({
      last_lesson_slug: "lesson-8",
      next_lesson_slug: null,
      completed_lesson_count: 8,
      lesson_count: 9,
    });

    expect(resumePoint(countsDisagree)).toEqual({ status: "finished" });
  });
});
