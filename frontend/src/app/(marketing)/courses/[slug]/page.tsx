import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CourseCard } from "@/components/catalogue/CourseCard";
import { Curriculum } from "@/components/catalogue/Curriculum";
import {
  CatalogueNotFound,
  publishedCourse,
  publishedCourseSlugs,
} from "@/lib/catalogue/courses";

/**
 * One course.
 *
 * **`dynamicParams = false` is the load-bearing line in this file.** By
 * default, a dynamic segment visited with a slug that `generateStaticParams`
 * did not produce is rendered *on demand* — a server invocation per request,
 * which is exactly what invariant 15 forbids. Setting it false makes those
 * slugs a static 404 instead.
 *
 * It is also abuse case 2's mechanism. An unpublished course must not be
 * reachable by guessing its slug, and without this line the first request for
 * `/courses/some-draft` would call the API at request time to find out.
 */
export const dynamicParams = false;

/**
 * Every published slug, at build time.
 *
 * Runs before any page in this segment is generated, so the whole catalogue is
 * known before the first course renders.
 */
export async function generateStaticParams() {
  const slugs = await publishedCourseSlugs();
  return slugs.map((slug) => ({ slug }));
}

/**
 * Loaded once per render pass.
 *
 * `generateMetadata` and the page both need the course, and Next calls them
 * separately. Next dedupes `fetch` for the same URL within a render, so this
 * is one request rather than two — but the reason it is written as a shared
 * function is legibility, not the dedupe: two copies of this `try/catch` would
 * be two places to get the 404 handling wrong.
 */
async function loadCourse(slug: string) {
  try {
    return await publishedCourse(slug);
  } catch (error) {
    // **Only a 404 becomes a missing page.** A 500 or a connection failure is
    // the API being broken, and abuse case 6 says that stops the build rather
    // than quietly publishing a site where a course turned into a 404.
    if (error instanceof CatalogueNotFound) notFound();
    throw error;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const course = await loadCourse(slug);

  return {
    title: course.title,
    // The catalogue description, not an invented one. An empty description is
    // better than a generated sentence that claims something about the course.
    description: course.description || undefined,
  };
}

export default async function CoursePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const course = await loadCourse(slug);
  const skills = Array.isArray(course.skill_areas) ? (course.skill_areas as string[]) : [];

  return (
    <article className="mx-auto flex max-w-3xl flex-col gap-12 px-6 py-16">
      <header className="flex flex-col gap-4">
        <p className="flex items-center gap-2 text-sm text-ink-subtle">
          <Link href="/courses" className="hover:text-ink">
            Courses
          </Link>
          <span aria-hidden="true">/</span>
          <span>{course.language.name}</span>
        </p>

        <h1 className="font-display text-4xl leading-tight tracking-tight text-ink">
          {course.title}
        </h1>

        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-muted">
          <span>{course.language.name}</span>
          <span aria-hidden="true">·</span>
          <span>Level {course.level}</span>
          {course.instructor_name && (
            <>
              <span aria-hidden="true">·</span>
              <span>{course.instructor_name}</span>
            </>
          )}
        </p>

        {course.description && (
          <p className="text-lg leading-relaxed text-ink-muted">{course.description}</p>
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
      </header>

      <section aria-labelledby="curriculum" className="flex flex-col gap-6">
        <h2 id="curriculum" className="font-display text-2xl text-ink">
          What is in the course
        </h2>
        <Curriculum sections={course.sections} />
      </section>

      {course.related.length > 0 && (
        <section aria-labelledby="related" className="flex flex-col gap-6">
          <h2 id="related" className="font-display text-2xl text-ink">
            Related courses
          </h2>
          <ul className="grid gap-5 sm:grid-cols-2">
            {course.related.map((related) => (
              <li key={related.slug}>
                <CourseCard course={related} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
