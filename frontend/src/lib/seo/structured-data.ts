import type { PublicCourseDetail } from "@/lib/catalogue/courses";
import { canonical } from "@/lib/site";

/**
 * `schema.org/Course` for a published course, built from stored facts only.
 *
 * Structured data is how a course can appear in search as something other than a
 * blue link. The whole risk of it is that the format invites claims a product cannot
 * back — which is why the omissions below are as deliberate as the fields.
 *
 * ## What is deliberately absent
 *
 * **`offers`.** The subscription price is unresolved (CLAUDE.md §11 #1), and an
 * `offers` block is the one part of this vocabulary that search engines surface as a
 * number next to the result. Inventing it is §6, and inventing it *in a search
 * result* travels further than inventing it anywhere else.
 *
 * **`aggregateRating` and `review`.** No ratings exist. Fabricating them is both §6
 * and, for what it is worth, against every search engine's own policy — but the
 * reason not to is the first one.
 *
 * **`hasCourseInstance`.** Requires a course mode and a schedule. This product has
 * neither: courses are self-paced and live classes are explicitly unapproved
 * (CLAUDE.md §11 #2).
 *
 * **`timeRequired` / `courseWorkload`.** The reason here used to be that no aggregate
 * existed. **It does now** — ADR-041 added `total_duration_seconds` to the course
 * detail response, derived in the catalogue and withheld (`null`) until every lesson
 * that counts has been measured. So the original objection is gone, and summing it in
 * the frontend is still the wrong move for the original reason: the catalogue owns the
 * figure.
 *
 * What is left is a deliberate omission rather than a blocked one. Emitting
 * `timeRequired` means choosing an ISO 8601 duration and deciding what a course with
 * `null` emits — nothing, or the property omitted — which is a structured-data
 * decision with search-result consequences, not a formatting detail. Not taken here.
 *
 * ## How it is rendered, and why that needed checking
 *
 * As a **plain text child** of `<script type="application/ld+json">`, never through
 * `dangerouslySetInnerHTML` — CLAUDE.md §6 forbids that on user-supplied content, and
 * a course title and description are exactly that: instructor-authored, then
 * admin-approved.
 *
 * **React escapes the one sequence that matters.** Verified against the build rather
 * than assumed: a course titled `Hostile </script><img src=x onerror=alert(1)>` is
 * emitted as `Hostile </script><img …>`. The `</script` is broken up by React's
 * own server renderer, so the string cannot terminate the element; the `<img>` stays
 * as text inside a JSON string in a non-executable script type, where it is inert.
 * `assert-page-structure.mjs` checks the built output parses as JSON and contains no
 * raw `</script`, because that property only exists in server-rendered HTML and no
 * jsdom test can see it.
 */

/** The product's own name, as it already appears in the header and share cards. */
const PROVIDER_NAME = "Lingua";

/**
 * Only string tags. `skill_areas` is a free-form `JSONField` whose generated type is
 * `unknown`, and `CourseCatalogue` guards it the same way — this is the third reader.
 */
function skillsOf(course: PublicCourseDetail): string[] {
  return Array.isArray(course.skill_areas)
    ? (course.skill_areas as unknown[]).filter((tag): tag is string => typeof tag === "string")
    : [];
}

/**
 * The JSON-LD object for a course, or the smallest honest version of it.
 *
 * Every optional field is omitted rather than emitted empty: `description: ""` and
 * `instructor: { name: "" }` are both claims that something exists and is blank,
 * which is worse than saying nothing. `url` is omitted when no origin is configured,
 * for the same reason ADR-035 omits canonicals in that state.
 */
export function courseStructuredData(course: PublicCourseDetail): Record<string, unknown> {
  const url = canonical(`/courses/${encodeURIComponent(course.slug)}/`);
  const skills = skillsOf(course);

  return {
    "@context": "https://schema.org",
    "@type": "Course",
    name: course.title,
    ...(course.description ? { description: course.description } : {}),
    inLanguage: course.language.code,
    educationalLevel: course.level,
    ...(skills.length > 0 ? { teaches: skills } : {}),
    ...(course.instructor_name
      ? { instructor: { "@type": "Person", name: course.instructor_name } }
      : {}),
    ...(url === null ? {} : { url }),
    provider: { "@type": "Organization", name: PROVIDER_NAME },
  };
}
