"use client";

import { buttonStyles } from "@/components/ui/Button";

/**
 * Downloading your own data.
 *
 * **A plain link, not a fetch.** `GET /api/v1/auth/me/export/` is same-origin
 * through the Next rewrite, so the session cookie rides along and the browser's own
 * download machinery handles the rest — the endpoint sends
 * `Content-Disposition: attachment`, so the browser names and saves the file.
 *
 * The alternative is `fetch`, `response.blob()`, `URL.createObjectURL` and a
 * synthetic click. That buys a spinner and costs: the whole export is held in
 * memory, the object URL has to be revoked, and a failure has to be rendered
 * somewhere. A link gets progress, resumption, the download shelf and the browser's
 * own error handling for free, and this component needs no client JavaScript at all.
 *
 * The client boundary permits reuse of `buttonStyles` from the shared client
 * control module. The link still prerenders and has no state or event handler;
 * the browser handles the download without a JavaScript fetch.
 *
 * `prefetch={false}` would be the concern with `next/link` — prefetching a data
 * export would download it on hover — so this is a plain `<a>`. Next's own lint rule
 * prefers `Link` for internal navigation and is wrong here: `/api/*` is not a Next
 * route, it is a rewrite to Django, and `Link` would try to route it client-side.
 */
export function DataExport() {
  return (
    <section aria-labelledby="your-data" className="flex flex-col gap-4">
      <h2 id="your-data" className="font-display text-2xl text-ink">
        Your data
      </h2>

      <div className="flex min-w-0 flex-col items-start gap-5 border-t border-line pt-5 [overflow-wrap:anywhere]">
        <p className="max-w-prose text-sm leading-relaxed text-ink-muted">
          A copy of everything this service holds about your account, as a JSON
          file: your details, the courses you have started, how far you have got,
          and your subscription history. Course content is not included.
        </p>

        <a
          href="/api/v1/auth/me/export/"
          // `download` is a hint the browser may ignore; the endpoint's
          // `Content-Disposition` is what actually makes this a save rather than a
          // page full of JSON. Both, because the attribute also names the file when
          // a browser does honour it.
          download
          className={buttonStyles({ variant: "secondary", lift: false })}
        >
          Download my data
        </a>

        {/*
         * Deletion is deliberately absent, and saying nothing would read as an
         * oversight rather than a decision.
         *
         * `docs/specs/m10-admin.md` §6: "Erasure obligations are real and are their
         * own piece of work." What survives an erasure — invoices, the audit trail,
         * content an instructor wrote — is a retention question with legal weight,
         * not an engineering one, and a button in front of an unanswered question is
         * worse than no button. ADR-036 §5.
         *
         * **And it does not name a way to ask, because there is not one.** The first
         * draft said "email support", which would have invented a support channel:
         * there is no support address anywhere in this repository, and a published
         * address nobody reads is worse than an admitted gap. It stays this way until
         * a real contact route exists.
         */}
        <p className="max-w-prose text-sm leading-relaxed text-ink-muted">
          Deleting an account is not yet something this site can do, and there is
          no contact route set up for asking. Both are being worked on.
        </p>
      </div>
    </section>
  );
}
