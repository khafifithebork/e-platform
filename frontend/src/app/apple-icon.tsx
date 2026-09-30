import { ImageResponse } from "next/og";

import { CARD_ACCENT, CARD_CORAL, CARD_ON_ACCENT } from "@/lib/share/card";

/**
 * The icon iOS uses when somebody adds this site to their home screen.
 *
 * **180×180 PNG, which is why it is generated rather than drawn.** ADR-035 §5 left
 * this out because it "needs a 180×180 PNG" and "authoring raster assets is not
 * something to improvise" — true when the only options were a drawing tool or a
 * committed binary. `ImageResponse` removes that constraint: the same mechanism the
 * share card uses produces this at build time, from the same brand values, with
 * nothing new installed.
 *
 * **No transparency and no rounded corners.** iOS masks a home-screen icon to its own
 * shape and paints its own background, so a rounded PNG shows corner artefacts inside
 * the mask and a transparent one renders black. The accent fills the square edge to
 * edge deliberately — `icon.svg` rounds itself because a browser tab does not mask.
 *
 * The dot is proportionally larger than the favicon's: at 180px a 12px dot is a
 * speck, and at the size iOS actually shows this it would disappear.
 */

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: CARD_ACCENT,
          color: CARD_ON_ACCENT,
          fontSize: 110,
          fontWeight: 600,
          position: "relative",
        }}
      >
        L
        <div
          style={{
            position: "absolute",
            top: 22,
            right: 22,
            width: 34,
            height: 34,
            borderRadius: 999,
            background: CARD_CORAL,
          }}
        />
      </div>
    ),
    size,
  );
}
