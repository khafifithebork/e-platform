import type { ReactNode } from "react";

/**
 * The two page-title treatments this app has, and what decides between them.
 *
 * **Both were already in the code; neither was written down.** Fourteen `<h1>`
 * elements carried a hand-written class string, in three variants — and the
 * third turned out to be an accident (`/my-courses` omitted `leading-tight`,
 * alone among the larger ones). The two deliberate ones split perfectly:
 *
 * - `page` — `/courses`, `/pricing`, a course, `/my-courses`, the landing hero.
 * - `interstitial` — the nine auth form states, the three `LessonGate`
 *   refusals, the 404.
 *
 * **The split is not about column width**, which is what it looks like from the
 * auth pages alone. `NotFoundContent` and `LessonGate`'s refusal both sit in a
 * `max-w-2xl` column at `text-3xl`, and the landing hero sits in the *same*
 * `max-w-2xl` column at `text-4xl sm:text-5xl`. What separates them is the kind
 * of page: a destination you navigated to, or an interstitial standing in for
 * one — a form step, a refusal, a page that is not there. An interstitial that
 * titles itself as loudly as the catalogue reads as shouting about bad news.
 *
 * Recorded here rather than inferred fourteen times, because a pattern that is
 * exceptionless in the code and absent from it is one edit from becoming a
 * pattern with an exception.
 */
export const PAGE_TITLE = {
  page: "font-display text-4xl leading-tight tracking-tight text-ink",
  interstitial: "font-display text-3xl leading-tight tracking-tight text-ink",
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
