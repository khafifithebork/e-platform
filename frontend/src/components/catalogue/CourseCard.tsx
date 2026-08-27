import Link from "next/link";

import type { PublicCourse } from "@/lib/catalogue/courses";

/**
 * One course, as it appears in a listing.
 *
 * Presentational and server-renderable: no state, no effects, no
 * `"use client"`. It is rendered inside a client component (the filter needs
 * state), which prerenders it anyway — but keeping the card itself free of
 * client concerns means it can be reused on the landing page and the course
 * detail page without dragging hydration along.
 *
 * **The whole card is not a link.** A link wrapping a heading, a paragraph and
 * a list of tags gives screen readers one enormous link name read out in full.
 * The title is the link; the rest is description, and `aria-labelledby` on the
 * article is what ties them together in the accessibility tree.
 */
export function CourseCard({ course }: { course: PublicCourse }) {
  const titleId = `course-${course.slug}-title`;
  const skills = Array.isArray(course.skill_areas) ? (course.skill_areas as string[]) : [];

  return (
    <article
      aria-labelledby={titleId}
      className="flex flex-col gap-3 rounded-[--radius-lg] border border-line
        bg-surface p-5 transition-colors hover:border-line-strong"
    >
      <div className="flex items-center gap-2 text-sm text-ink-subtle">
        <span>{course.language.name}</span>
        <span aria-hidden="true">·</span>
        {/*
         * The CEFR level is an abbreviation nobody outside language teaching
         * reads aloud correctly. `<abbr>` gives it an expansion without
         * spending a line of the card on it.
         */}
        <abbr title={LEVEL_NAMES[course.level] ?? course.level} className="no-underline">
          {course.level}
        </abbr>
      </div>

      <h3 id={titleId} className="font-display text-xl leading-snug text-ink">
        <Link href={`/courses/${course.slug}`} className="hover:text-accent">
          {course.title}
        </Link>
      </h3>

      {course.description && (
        <p className="line-clamp-3 text-sm leading-relaxed text-ink-muted">
          {course.description}
        </p>
      )}

      {/*
       * "Empty when they have not set one" — the API says so, and rendering
       * "by " with nothing after it is the kind of thing that only shows up
       * on the one instructor who never filled in their profile.
       */}
      {course.instructor_name && (
        <p className="text-sm text-ink-subtle">{course.instructor_name}</p>
      )}

      {skills.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {skills.map((skill) => (
            <li
              key={skill}
              className="rounded-[--radius-sm] bg-surface-sunken px-2 py-0.5
                text-xs text-ink-muted"
            >
              {skill}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

/**
 * CEFR levels spelled out.
 *
 * Hard-coded rather than fetched: these are a published standard, not our
 * data, and the API returns the code alone. A missing key falls back to the
 * code itself, so a level added server-side degrades to what it already was
 * rather than rendering `undefined`.
 */
const LEVEL_NAMES: Record<string, string> = {
  A1: "A1 — Beginner",
  A2: "A2 — Elementary",
  B1: "B1 — Intermediate",
  B2: "B2 — Upper intermediate",
  C1: "C1 — Advanced",
  C2: "C2 — Proficient",
};
