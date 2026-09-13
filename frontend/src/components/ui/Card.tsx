"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ElementType } from "react";

import { cn } from "@/lib/utils/cn";

/**
 * React's native `onDrag`/`onDragStart`/`onDragEnd` (drag-and-drop events)
 * collide, by name only, with framer-motion's gesture props of the same
 * name (pointer-drag). Nothing that renders a `Card` uses either, so they
 * are excluded from what a caller may pass — the alternative is `tsc`
 * refusing every other prop over a conflict this component never exercises.
 */
type CardProps = Omit<
  React.HTMLAttributes<HTMLElement>,
  "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd"
> & {
  as?: ElementType;
  /** Lifts on hover — for a card that is itself a link's whole surface. */
  hoverable?: boolean;
};

/**
 * The one bordered, elevated container this design uses.
 *
 * Every card-like element in the app — a course, a plan, an enrolment — was a
 * `<div className="rounded-[--radius-lg] border border-line bg-surface p-5">`
 * repeated at each call site with small drifts. One primitive means a change
 * to how a card looks, or how it responds to a pointer, is one file.
 *
 * **`hoverable` lifts with a spring, not a CSS transition.** A `transition:
 * transform 150ms ease` gets there at a constant rate and stops dead; a
 * spring overshoots very slightly and settles, which is the difference
 * between a card that was *styled* to move and one that behaves like an
 * object with a little weight. `useReducedMotion` opts out to a plain
 * element with no motion props at all, rather than a spring with zero
 * stiffness — the safest way to guarantee nothing animates.
 *
 * Only the three tags this app actually renders a `Card` as get a motion
 * component. `motion.create(Tag)` for an arbitrary runtime `Tag` would
 * construct a new component type on every render — React would then remount
 * the node each time instead of animating it — so this is a fixed lookup, not
 * a dynamic wrap.
 */
const MOTION_TAGS = {
  div: motion.div,
  article: motion.article,
  section: motion.section,
} as const;

export function Card({ as = "div", className, hoverable = false, ...props }: CardProps) {
  const reduceMotion = useReducedMotion();
  const base = "rounded-[--radius-lg] border border-line bg-surface p-5";

  if (!hoverable || reduceMotion || typeof as !== "string" || !(as in MOTION_TAGS)) {
    const Tag = as;
    return (
      <Tag
        className={cn(
          base,
          "shadow-[--shadow-sm]",
          hoverable && "transition-[border-color,box-shadow] duration-150 hover:border-line-strong hover:shadow-[--shadow-md]",
          className,
        )}
        {...props}
      />
    );
  }

  const MotionTag = MOTION_TAGS[as as keyof typeof MOTION_TAGS];

  return (
    <MotionTag
      className={cn(base, "border-line", className)}
      initial={{ boxShadow: "var(--shadow-sm)" }}
      whileHover={{
        y: -4,
        borderColor: "var(--color-line-strong)",
        boxShadow: "var(--shadow-md)",
      }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      {...props}
    />
  );
}
