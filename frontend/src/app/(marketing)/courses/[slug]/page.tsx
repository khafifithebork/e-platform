import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CourseCard } from "@/components/catalogue/CourseCard";
import { CourseProgress } from "@/components/catalogue/CourseProgress";
import { Curriculum } from "@/components/catalogue/Curriculum";
import { StaggerItem, StaggerList } from "@/components/motion/StaggerList";
import { Badge } from "@/components/ui/Badge";
import { PageTitle } from "@/components/ui/PageTitle";
import {
  CatalogueNotFound,
  publishedCourse,
  publishedCourseSlugs,
} from "@/lib/catalogue/courses";
import { courseStructuredData } from "@/lib/seo/structured-data";
import { publicMetadata } from "@/lib/site";

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

  return publicMetadata({
    title: course.title,
    /*
     * The catalogue description, not an invented one — the original decision
     * here, kept.
     *
     * **What an empty one actually renders is inheritance, not absence**, and the
     * comment this replaces implied otherwise. `publicMetadata` omits the key, and
     * Next then falls back to the root layout's site description, so a course with
     * no description ships "Curated language courses, reviewed before
     * publication…" as its own. Verified in the built HTML, not assumed: `t8-spanish`
     * has `description: ""` today and that is exactly what it emits.
     *
     * That is acceptable — the sentence is true of the site and says nothing false
     * about the course — and it is *not* the same as having no description. The
     * alternative worth considering later is assembling one from facts the API does
     * have (title, level, language), which is composition rather than invention.
     * Out of scope here; §6 forbids the third option of making something up.
     */
    description: course.description || undefined,
    // The canonical form Django and `trailingSlash: true` both serve. Encoded the
    // same way `sitemap.ts` encodes it, so the two cannot disagree about a slug
    // with anything unusual in it.
    path: `/courses/${encodeURIComponent(slug)}/`,
  });
}

export default async function CoursePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const course = await loadCourse(slug);
  const skills = Array.isArray(course.skill_areas) ? (course.skill_areas as string[]) : [];

  return (
    <article className="mx-auto flex max-w-3xl flex-col gap-12 px-6 py-16">
      {/*
       * `schema.org/Course`, from stored facts only.
       *
       * **A plain text child, never `dangerouslySetInnerHTML`.** A course title and
       * description are instructor-authored and then admin-approved — user-supplied
       * content twice over, which CLAUDE.md §6 forbids injecting as markup. React's
       * server renderer escapes the one sequence that could terminate this element:
       * verified against built output, a title containing `</script>` is emitted as
       * `</script>`.
       *
       * What this deliberately does *not* claim — no `offers`, no `aggregateRating`,
       * no schedule — is documented in `lib/seo/structured-data.ts`, and it is the
       * more important half.
       */}
      <script type="application/ld+json">{JSON.stringify(courseStructuredData(course))}</script>

      <header className="flex flex-col gap-4">
        <p className="flex items-center gap-2 text-sm text-ink-subtle">
          <Link href="/courses" className="hover:text-ink">
            Courses
          </Link>
          <span aria-hidden="true">/</span>
          <span>{course.language.name}</span>
        </p>

        <PageTitle>{course.title}</PageTitle>

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
              <li key={skill}>
                <Badge>{skill}</Badge>
              </li>
            ))}
          </ul>
        )}
      </header>

      {/*
       * The one personalised strip on a statically generated page.
       *
       * A client component, so the prerendered HTML stays identical for
       * everyone and invariant 15 holds. It renders nothing for a visitor who
       * is not enrolled — which is most of them, on a public catalogue page.
       */}
      <CourseProgress courseSlug={course.slug} />

      <section aria-labelledby="curriculum" className="flex flex-col gap-6">
        <h2 id="curriculum" className="font-display text-2xl text-ink">
          What is in the course
        </h2>
        <Curriculum sections={course.sections} courseSlug={course.slug} />
      </section>

      {course.related.length > 0 && (
        <section aria-labelledby="related" className="flex flex-col gap-6">
          <h2 id="related" className="font-display text-2xl text-ink">
            Related courses
          </h2>
          <StaggerList className="grid gap-5 sm:grid-cols-2">
            {course.related.map((related) => (
              <StaggerItem key={related.slug}>
                <CourseCard course={related} />
              </StaggerItem>
            ))}
          </StaggerList>
        </section>
      )}
    </article>
  );
}
