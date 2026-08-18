import type { Metadata } from "next";

import "./globals.css";

/*
 * No `next/font/google`.
 *
 * create-next-app wires up Geist from Google Fonts, which means every build
 * needs to reach fonts.googleapis.com. On a machine that cannot — this one —
 * the build emits a warning and silently substitutes a fallback, so the font
 * you tested is not the font you shipped. A system stack is honest about what
 * it renders, costs no request, and cannot shift layout on load.
 *
 * If a licensed brand face is chosen later, self-host it with
 * `next/font/local` rather than reintroducing the network dependency.
 */
export const metadata: Metadata = {
  title: {
    default: "Lingua",
    template: "%s · Lingua",
  },
  description:
    "Curated language courses, reviewed before publication. Video and audio lessons with transcripts.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
