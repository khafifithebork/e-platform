import type { ElementType, HTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

/**
 * The one bordered, elevated container this design uses.
 *
 * Every card-like element in the app — a course, a plan, an enrolment — was a
 * `<div className="rounded-[--radius-lg] border border-line bg-surface p-5">`
 * repeated at each call site with small drifts (`p-5` here, `p-6` there). One
 * primitive means a change to how a card looks is one file, not an audit of
 * every place someone typed the recipe from memory.
 *
 * **Not a wrapper that forces `<div>`.** `CourseCard` and `Plan` are
 * `<article>` and `<section>` because they are landmarks with a heading
 * (`aria-labelledby`), not generic containers — so this renders as whatever
 * tag the caller needs and only contributes the class names.
 */
export function Card({
  as: Tag = "div",
  className,
  hoverable = false,
  ...props
}: HTMLAttributes<HTMLElement> & {
  as?: ElementType;
  /** Lifts on hover — for a card that is itself a link's whole surface. */
  hoverable?: boolean;
}) {
  return (
    <Tag
      className={cn(
        "rounded-[--radius-lg] border border-line bg-surface p-5 shadow-[--shadow-sm]",
        "transition-[border-color,box-shadow,transform] duration-150",
        hoverable && "hover:-translate-y-0.5 hover:border-line-strong hover:shadow-[--shadow-md]",
        className,
      )}
      {...props}
    />
  );
}
