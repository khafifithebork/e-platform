import type { Enrollment } from "@/lib/api/client";

/**
 * Where a learner picks a course back up, decided in one place.
 *
 * **Two components were deciding this independently**, with the same three rules
 * and near-identical paragraphs of comment explaining them: `MyCourses`'
 * enrolment cards and `CourseProgress`, the strip on a public course page. Both
 * read the same fields, both derived "finished" the same way, and both explained
 * the bookmark distinction in their own words. Two copies of a rule with two
 * copies of the reasoning is the shape that drifts — and the drift would be
 * quiet, because each component looks right on its own.
 *
 * The three rules, stated once:
 *
 * 1. **Finished means no next lesson.** `next_lesson_slug` is null only when
 *    nothing is left, so a course with an enrolment and no next lesson is
 *    complete. Offering "resume" there sends somebody back into a course they
 *    have already finished.
 *
 * 2. **Resume points at `next_lesson`, never `last_lesson`.** They differ for
 *    anyone who skipped ahead: the bookmark is where they *were*, the next
 *    lesson is the earliest *unfinished* one. The selector that computes it
 *    walks back deliberately, so a learner who jumped forward is not written
 *    off — and following the bookmark instead would undo that on the client.
 *
 * 3. **`started` is whether anything has actually been watched**, which is
 *    `last_lesson_slug`, not the enrolment itself. Enrolment happens by opening
 *    a lesson, so a course can be enrolled-in and never watched — and calling
 *    that "continue" describes something that did not happen.
 *
 * What is deliberately *not* here is the wording. `MyCourses` says "Continue" on
 * a card in a list and `CourseProgress` says "Continue where you left off" in a
 * one-line strip; both are right for their context, and pulling them in here
 * would trade a duplicated rule for a shared string that fits neither well.
 */
export type ResumePoint =
  | { status: "finished" }
  | {
      status: "resume";
      /** The lesson to open — the earliest unfinished one. */
      href: string;
      /** True once any lesson has been watched. Decides continue-vs-start wording. */
      started: boolean;
    };

export function resumePoint(enrollment: Enrollment): ResumePoint {
  if (enrollment.next_lesson_slug === null) return { status: "finished" };

  return {
    status: "resume",
    href: `/courses/${enrollment.course_slug}/lessons/${enrollment.next_lesson_slug}`,
    started: enrollment.last_lesson_slug !== null,
  };
}
