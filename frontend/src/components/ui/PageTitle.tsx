import type { ReactNode } from "react";

/**
 * The page-title treatments this app has, and what decides between them.
 *
 * **All of them were already in the code; none was written down.** Fifteen
 * `<h1>` elements carried a hand-written class string, and unpicking which
 * differences were decisions took two passes:
 *
 * - `page` — `/courses`, `/pricing`, a course, `/my-courses`, the landing hero.
 * - `interstitial` — the nine auth form states, the three `LessonGate`
 *   refusals, the 404.
 * - `section` — one site, `LessonPlayer`. See below.
 *
 * `/my-courses` was a sixteenth variant by accident: it omitted `leading-tight`,
 * alone among the larger titles.
 *
 * **The split is not about column width**, which is what it looks like from the
 * auth pages alone. `NotFoundContent` and `LessonGate`'s refusal both sit in a
 * `max-w-2xl` column at `text-3xl`, and the landing hero sits in the *same*
 * `max-w-2xl` column at `text-4xl sm:text-5xl`. What separates them is the kind
 * of page: a destination you navigated to, or an interstitial standing in for
 * one — a form step, a refusal, a page that is not there. An interstitial that
 * titles itself as loudly as the catalogue reads as shouting about bad news.
 *
 * **`section` is the one that is recorded rather than decided.** `LessonPlayer`
 * titles the lesson with a string byte-identical to the `<h2>` section headings
 * on the marketing pages — no `tracking-tight`, no `leading-tight`, a step
 * smaller again. Read generously that is right: inside the player the video is
 * the subject and the title is a label on it, not a title over it. Read
 * unkindly it is a heading written before there was a scale to write it
 * against.
 *
 * It is reproduced here exactly, so adopting the component changed nothing on
 * screen, and it is deliberately *not* normalised into the other two: adding
 * `tracking-tight` to a 24px heading is visible, and it would also pull the
 * lesson title away from the `<h2>`s it currently matches. Whether the lesson
 * title should stay a step below an interstitial is a design question, flagged
 * rather than answered.
 *
 * Recorded here rather than inferred fifteen times, because a pattern that is
 * consistent in the code and absent from it is one edit from growing an
 * exception — and, as `section` shows, an exception is easy to miss even when
 * you are looking for them.
 */
export const PAGE_TITLE = {
  page: "font-display text-4xl leading-tight tracking-tight text-ink",
  interstitial: "font-display text-3xl leading-tight tracking-tight text-ink",
  section: "font-display text-2xl text-ink",
} as const;

export type PageTitleVariant = keyof typeof PAGE_TITLE;

/**
 * A page's `<h1>`.
 *
 * `PAGE_TITLE` is exported separately for the one caller that cannot use this
 * component: the landing hero's title is a `motion.h1` carrying stagger
 * variants, and it takes one extra step at `sm:`. Composing the constant there
 * keeps it inside the system rather than outside it with a comment promising it
 * matches.
 */
export function PageTitle({
  children,
  variant = "page",
  id,
}: {
  children: ReactNode;
  variant?: PageTitleVariant;
  /** For an `aria-labelledby` that points at the title. */
  id?: string;
}) {
  return (
    <h1 id={id} className={PAGE_TITLE[variant]}>
      {children}
    </h1>
  );
}
