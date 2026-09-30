/**
 * `schema.org/Course`, and the claims it must not make.
 *
 * The fields are easy; the omissions are the reason this file is long. Structured
 * data is the one place a fabricated fact appears *inside a search result*, which
 * travels further than the same fabrication on a page — so each absence is asserted
 * rather than assumed.
 *
 * **Escaping is not tested here, and cannot be.** The property that matters — that a
 * course title containing `</script>` cannot terminate the element — is produced by
 * React's *server* renderer. jsdom sets text content through the DOM, where no parser
 * is involved and no escaping is needed, so a passing test here would prove nothing
 * about the built page. `assert-page-structure.mjs` checks it on real output.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicCourseDetail } from "@/lib/catalogue/courses";
import { courseStructuredData } from "@/lib/seo/structured-data";

const ORIGIN = "https://lingua.example";

function course(overrides: Partial<PublicCourseDetail> = {}): PublicCourseDetail {
  return {
    slug: "spanish",
    title: "Spanish for beginners",
    description: "Reviewed before publication.",
    language: { code: "es", name: "Spanish", native_name: "Español" },
    level: "A1",
    skill_areas: ["speaking", "listening"],
    instructor_name: "A. Teacher",
    ...overrides,
  } as PublicCourseDetail;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("what it says", () => {
  it("carries the stored facts", () => {
    vi.stubEnv("SITE_URL", ORIGIN);

    const data = courseStructuredData(course());

    expect(data).toMatchObject({
      "@context": "https://schema.org",
      "@type": "Course",
      name: "Spanish for beginners",
      description: "Reviewed before publication.",
      inLanguage: "es",
      educationalLevel: "A1",
      teaches: ["speaking", "listening"],
      instructor: { "@type": "Person", name: "A. Teacher" },
      url: "https://lingua.example/courses/spanish/",
      provider: { "@type": "Organization", name: "Lingua" },
    });
  });

  it("names the provider without asserting an identity it does not have", () => {
    /**
     * `provider` is the product name already on screen in the header and the share
     * cards. No address, no legal name, no `sameAs`, no logo URL — none of those is
     * established, and §6 forbids inventing a business identity.
     */
    vi.stubEnv("SITE_URL", ORIGIN);

    const provider = courseStructuredData(course()).provider as Record<string, unknown>;

    expect(Object.keys(provider).sort()).toEqual(["@type", "name"]);
  });
});

describe("what it must never say", () => {
  it("makes no price, rating, review or schedule claim", () => {
    /**
     * **The assertion this module exists for.** `offers` is the field a search engine
     * renders as a number beside the result, and the subscription price is unresolved
     * (§11 #1). `aggregateRating` and `review` describe feedback that does not exist.
     * `hasCourseInstance` needs a schedule, and live classes are explicitly
     * unapproved (§11 #2).
     */
    vi.stubEnv("SITE_URL", ORIGIN);

    const data = courseStructuredData(course());

    for (const forbidden of [
      "offers",
      "aggregateRating",
      "review",
      "reviews",
      "ratingValue",
      "hasCourseInstance",
      "timeRequired",
      "courseWorkload",
      "coursePrerequisites",
      "educationalCredentialAwarded",
    ]) {
      expect(data, forbidden).not.toHaveProperty(forbidden);
    }
  });

  it("says nothing at all about duration, which no aggregate exposes", () => {
    // `MediaAsset.duration_seconds` exists per lesson, but `total_duration_seconds`
    // was deferred by ADR-007 §4. Summing it here would be a second definition of a
    // figure the catalogue is meant to own.
    vi.stubEnv("SITE_URL", ORIGIN);

    expect(JSON.stringify(courseStructuredData(course()))).not.toMatch(/duration/i);
  });
});

describe("fields that may be missing", () => {
  it("omits the description rather than declaring an empty one", () => {
    // `t8-spanish` has `description: ""` today. An empty string is a claim that a
    // description exists and is blank.
    vi.stubEnv("SITE_URL", ORIGIN);

    expect(courseStructuredData(course({ description: "" }))).not.toHaveProperty("description");
  });

  it("omits the instructor when the API sends an empty name", () => {
    // The API documents `instructor_name` as empty when unset, which is why
    // `CourseCard` guards it too.
    vi.stubEnv("SITE_URL", ORIGIN);

    expect(courseStructuredData(course({ instructor_name: "" }))).not.toHaveProperty("instructor");
  });

  it("omits `teaches` when nothing is tagged, and filters non-strings", () => {
    // `skill_areas` is a `JSONField`: the generated type is `unknown` and the stored
    // value is whatever was written.
    vi.stubEnv("SITE_URL", ORIGIN);

    expect(courseStructuredData(course({ skill_areas: [] }))).not.toHaveProperty("teaches");
    expect(
      courseStructuredData(course({ skill_areas: ["speaking", 7] as unknown as [] })).teaches,
    ).toEqual(["speaking"]);
    expect(
      courseStructuredData(course({ skill_areas: { not: "a list" } as unknown as [] })),
    ).not.toHaveProperty("teaches");
  });

  it("omits the url when no origin is configured, rather than pointing at localhost", () => {
    /**
     * The same fail-safe ADR-035 applies to canonicals, for the same reason: with no
     * `SITE_URL` the site is not indexable at all, and a structured-data `url`
     * pointing at a developer's machine is a claim about where the course lives.
     */
    vi.stubEnv("SITE_URL", "");

    const data = courseStructuredData(course());

    expect(data).not.toHaveProperty("url");
    expect(JSON.stringify(data)).not.toMatch(/localhost/);
    // Still describes the course — the absence of an address is not a reason to say
    // nothing about it.
    expect(data).toHaveProperty("name", "Spanish for beginners");
  });

  it("encodes a slug the same way the canonical and the sitemap do", () => {
    vi.stubEnv("SITE_URL", ORIGIN);

    expect(courseStructuredData(course({ slug: "français b1" })).url).toBe(
      "https://lingua.example/courses/fran%C3%A7ais%20b1/",
    );
  });
});
