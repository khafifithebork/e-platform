import { ImageResponse } from "next/og";

import {
  CARD_ACCENT,
  CARD_CORAL,
  CARD_INK,
  CARD_INK_MUTED,
  CARD_ON_ACCENT,
  CARD_PAPER,
  CARD_SIZE,
} from "@/lib/share/card";

/**
 * The card a shared link to this site shows.
 *
 * **Generated at build time**, which is what makes this compatible with invariant 15:
 * Next's own documentation says an `opengraph-image` route is "statically optimized"
 * unless it uses a request-time API, and this uses none — no `headers()`, no
 * `searchParams`, no uncached fetch. The output is a PNG file beside the page.
 *
 * **`next/og` rather than a drawn asset**, decided 2026-09-30. It ships with Next —
 * `node_modules/next/og.js`, no `satori` or `resvg` in `package.json` — so §5 is
 * clear, and the same mechanism produces `apple-icon.tsx`, which removes the other
 * brand-asset gap without adding raster tooling to the project.
 *
 * ADR-035 §5 listed both as deliberately left out, on the grounds that "a link
 * preview without an image is plain; one pointing at an image that does not exist is
 * broken" and that generating one needed a decision nobody had made. This is that
 * decision.
 *
 * Colours come from `lib/share/card.ts` as literals, because there is no stylesheet
 * here — and `seo.test.ts` asserts they still match the tokens, the same guard
 * `icon.svg` has.
 */

export const alt = "Lingua — curated language courses, reviewed before publication";
export const size = CARD_SIZE;
export const contentType = "image/png";

export default function Image() {
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
        {/* The wordmark, redrawn in flexbox because this renderer has no SVG
            `<text>` and no access to `icon.svg`. Same geometry: a 96px square at
            24px radius, the glyph, and the coral dot. */}
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <div
            style={{
              position: "relative",
              display: "flex",
              width: 96,
              height: 96,
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 24,
              background: CARD_ACCENT,
              color: CARD_ON_ACCENT,
              fontSize: 56,
              fontWeight: 600,
            }}
          >
            L
            <div
              style={{
                position: "absolute",
                top: -6,
                right: -6,
                width: 32,
                height: 32,
                borderRadius: 999,
                background: CARD_CORAL,
                border: `6px solid ${CARD_PAPER}`,
              }}
            />
          </div>
          <div style={{ fontSize: 56, fontWeight: 600, color: CARD_INK }}>Lingua</div>
        </div>

        {/*
         * The same claim the landing page makes, and the only one it makes that the
         * code can keep. No price, no learner count, no testimonial — a share card is
         * the most copied surface a product has, and an invented number on one
         * travels further than anywhere else it could appear (§6).
         */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 64, fontWeight: 600, color: CARD_INK, lineHeight: 1.1 }}>
            Curated language courses
          </div>
          <div style={{ fontSize: 34, color: CARD_INK_MUTED }}>
            Every course is reviewed before it is published.
          </div>
        </div>
      </div>
    ),
    size,
  );
}
