"use client";

import { useEffect } from "react";

import { reportBoundaryError } from "@/lib/observability/sentry";

/**
 * The last resort: the root layout itself threw.
 *
 * ADR-031 §2. This **replaces the document**, so it carries its own `<html>` and
 * `<body>` — which also means it cannot use `SiteShell`, the tokens applied to
 * `body`, or `PageTitle`.
 *
 * **That is why it is deliberately plain, and why the styles are inline.** A
 * last-resort page that needs the design system to work is a last-resort page
 * that fails when the design system is the thing that broke — and the one
 * scenario this file exists for is the root layout failing to render, which is
 * where a stylesheet or a provider is the likely culprit. The cost is one page
 * whose styling is maintained separately and will drift from the rest; that is
 * accepted, because the alternative is a fallback that depends on what failed.
 *
 * `lang="en"` is hardcoded here for the same reason it is in the root layout
 * (ADR-033 §1 — interface language is English and no locale is approved).
 *
 * No colour tokens, so no dark scheme: `color-scheme` and the palette both live
 * in `globals.css`, which this page cannot assume loaded. System colours only.
 */
export default function GlobalError({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    reportBoundaryError(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          padding: "4rem 1.5rem",
          fontFamily: "system-ui, sans-serif",
          lineHeight: 1.6,
        }}
      >
        <main style={{ maxWidth: "36rem", marginInline: "auto" }}>
          <h1 style={{ fontSize: "1.875rem", lineHeight: 1.25, margin: "0 0 1rem" }}>
            Something went wrong
          </h1>

          <p style={{ margin: "0 0 1.5rem" }}>
            Lingua could not load. This is a fault on our side, not something you
            did. Reloading may be enough; if it is not, it should be working again
            shortly.
          </p>

          {/*
           * A plain link, not a `reset()` button. When the root layout is what
           * failed, re-rendering the same tree is unlikely to help — a full
           * document load is the thing worth offering. And an `<a>` works
           * without the JavaScript that may itself be the problem.
           *
           * `no-html-link-for-pages` is disabled here, and this is the one place
           * that rule is wrong. It exists to stop a full page reload where
           * client-side navigation would do — but `next/link` needs the router,
           * and this file renders precisely when the root of the application
           * failed to mount. A soft navigation that depends on what just broke is
           * not a way out. The full reload is the feature.
           */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a href="/" style={{ textDecoration: "underline" }}>
            Reload the home page
          </a>
        </main>
      </body>
    </html>
  );
}
