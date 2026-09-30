import { ImageResponse } from "next/og";

import { CatalogueNotFound, publishedCourse, publishedCourseSlugs } from "@/lib/catalogue/courses";
import {
  CARD_ACCENT,
  CARD_CORAL,
  CARD_INK,
  CARD_INK_MUTED,
  CARD_ON_ACCENT,
  CARD_PAPER,
  CARD_SIZE,
  courseCardText,
} from "@/lib/share/card";

/**
 * The card a shared link to one course shows.
 *
 * **The highest-value one of the three**, because a course page is what somebody
 * actually sends to a friend. The site card is what a link to the homepage gets, and
 * far fewer of those are shared.
 *
 * **Read at build time, through the same function the page uses.** `publishedCourse`
 * runs in CI where Django is reachable (invariant 15), and `generateStaticParams`
 * below mirrors the page's, so one PNG is produced per published course and no
 * request-time fetch exists to make this dynamic.
 *
 * Duplicating `generateStaticParams` rather than importing the page's is deliberate:
 * an image route and a page are separate route handlers, and Next resolves each
 * one's params independently. Both read `publishedCourseSlugs`, so there is one
 * definition of "published" even though there are two call sites.
 *
 * What the card *says* is decided in `lib/share/card.ts`, where it can be tested —
 * this file is layout. A PNG stream out of WASM is not something a unit test reads.
 */

export const alt = "A course on Lingua";
export const size = CARD_SIZE;
export const contentType = "image/png";

/**
 * **The load-bearing line, and `verify:static` is what said so.**
 *
 * Without it this route prerenders the known slugs *and* keeps a dynamic fallback for
 * the rest — which makes it a server-rendered route under `(marketing)`, breaking
 * invariant 15. The page beside it carries the same declaration for the same reason;
 * an image route is a separate route handler and does not inherit it.
 *
 * Caught by `scripts/assert-static-marketing.mjs` on the first build after this file
 * existed: "dynamic segment with fallback null; expected false". Nothing else would
 * have noticed, because the build succeeds either way.
 */
export const dynamicParams = false;

export async function generateStaticParams() {
  return (await publishedCourseSlugs()).map((slug) => ({ slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  let course;
  try {
    course = await publishedCourse(slug);
  } catch (error) {
    // A course that is no longer published has no card. Anything else is the API
    // being broken, which must stop the build rather than ship a site whose share
    // images quietly became placeholders — the same rule the page follows.
    if (error instanceof CatalogueNotFound) return new Response(null, { status: 404 });
    throw error;
  }

  const { title, subtitle } = courseCardText(course);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: CARD_PAPER,
          padding: 80,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/*
           * The language and level first, small. Somebody deciding whether to open a
           * shared link wants to know "Spanish, beginner" before they read a title,
           * and these two are the fields that are never empty — unlike the
           * description, which `t8-spanish` does not have.
           */}
          <div style={{ fontSize: 32, color: CARD_INK_MUTED }}>{subtitle}</div>
          <div style={{ fontSize: 68, fontWeight: 600, color: CARD_INK, lineHeight: 1.1 }}>
            {title}
          </div>
        </div>

        {/* The mark, smaller than on the site card: here the course is the subject and
            this is the byline. */}
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              position: "relative",
              display: "flex",
              width: 64,
              height: 64,
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 16,
              background: CARD_ACCENT,
              color: CARD_ON_ACCENT,
              fontSize: 38,
              fontWeight: 600,
            }}
          >
            L
            <div
              style={{
                position: "absolute",
                top: -4,
                right: -4,
                width: 22,
                height: 22,
                borderRadius: 999,
                background: CARD_CORAL,
                border: `4px solid ${CARD_PAPER}`,
              }}
            />
          </div>
          <div style={{ fontSize: 30, color: CARD_INK_MUTED }}>
            Reviewed before publication
          </div>
        </div>
      </div>
    ),
    size,
  );
}
