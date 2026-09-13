"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

/**
 * A grid or list whose items rise in one after another, rather than all at
 * once. `StaggerList` owns the timing on the container; each child that
 * should participate wraps itself in `StaggerItem`.
 *
 * **Kept as a real `<ul>`/`<li>` pair.** `motion.ul` and `motion.li` render
 * the actual element with animation props layered on — this is not a `<div>`
 * grid pretending to be a list, which matters here specifically: every
 * course/enrolment grid this wraps is read by a screen reader as a list of N
 * items, and swapping the tag to animate it would take that away.
 */
const container: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const item: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] } },
};

/**
 * React's native DOM event types and framer-motion's animation/gesture props
 * share five names with incompatible signatures — React's are DOM events
 * (drag-and-drop, CSS animation events), framer-motion's are pointer
 * gestures and animation-definition callbacks. This app never passes any of
 * them to these components; excluding them is what lets `motion.ul`/`motion.li`
 * accept everything else a caller does pass (`aria-label`, `id`, …) without
 * `tsc` refusing the whole prop bag over a conflict nobody uses.
 */
type SafeListProps<Tag extends "ul" | "li"> = Omit<
  ComponentPropsWithoutRef<Tag>,
  "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd"
> & { children: ReactNode };

export function StaggerList({
  children,
  className,
  ...props
}: SafeListProps<"ul">) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return (
      <ul className={className} {...props}>
        {children}
      </ul>
    );
  }

  return (
    <motion.ul
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-40px" }}
      variants={container}
      className={className}
      {...props}
    >
      {children}
    </motion.ul>
  );
}

export function StaggerItem({
  children,
  className,
  ...props
}: SafeListProps<"li">) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return (
      <li className={className} {...props}>
        {children}
      </li>
    );
  }

  return (
    <motion.li variants={item} className={className} {...props}>
      {children}
    </motion.li>
  );
}
