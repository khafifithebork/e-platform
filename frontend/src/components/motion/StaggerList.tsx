"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

/**
 * A grid or list whose items rise in one after another, rather than all at
 * once. `StaggerList` owns the timing on the container; each child that
 * should participate wraps itself in `StaggerItem`.
 *
 * **Renders whichever tag the caller needs, from a fixed set.** The default
 * (`ul`/`li`) covers every course and enrolment grid this wraps — real
 * lists, read by a screen reader as a list of N items, which is why the
 * primitive renders the actual element rather than a `<div>` grid animated to
 * look like one. `dl`/`div` covers the one place this app stagger-reveals a
 * description list instead.
 *
 * **Not a generic `as` prop.** A `motion.create(Tag)` call for a runtime tag
 * string would construct a new component type on every render — React would
 * then remount the node instead of animating it, the same reasoning `Card`
 * documents for its own `as`. A fixed lookup of the two concrete tags this
 * app actually needs sidesteps both that and the generic-prop type puzzle a
 * parameterised version turned into (React's per-element HTML attribute
 * types don't unify cleanly under one type parameter without widening back to
 * `any`, which would silently drop the very prop-conflict checking `Card`'s
 * version exists to keep).
 */
const listVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] } },
};

/**
 * React's native DOM event types and framer-motion's animation/gesture props
 * share five names with incompatible signatures. Nothing that renders these
 * components passes any of the five; excluding them is what lets `motion.ul`
 * accept everything else a caller does pass without `tsc` refusing the whole
 * prop bag over a conflict nobody uses.
 */
type Excluded = "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd";

export function StaggerList({
  as = "ul",
  children,
  className,
  ...props
}: Omit<React.HTMLAttributes<HTMLElement>, Excluded> & {
  as?: "ul" | "dl";
  children: ReactNode;
}) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    const Plain = as;
    return (
      <Plain className={className} {...props}>
        {children}
      </Plain>
    );
  }

  const Motion = as === "dl" ? motion.dl : motion.ul;

  return (
    <Motion
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-40px" }}
      variants={listVariants}
      className={className}
      {...props}
    >
      {children}
    </Motion>
  );
}

export function StaggerItem({
  as = "li",
  children,
  className,
  ...props
}: Omit<React.HTMLAttributes<HTMLElement>, Excluded> & {
  as?: "li" | "div";
  children: ReactNode;
}) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    const Plain = as;
    return (
      <Plain className={className} {...props}>
        {children}
      </Plain>
    );
  }

  const Motion = as === "div" ? motion.div : motion.li;

  return (
    <Motion variants={itemVariants} className={className} {...props}>
      {children}
    </Motion>
  );
}
