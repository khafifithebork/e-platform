"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Fade-and-rise on scroll into view, once.
 *
 * **`globals.css`'s `prefers-reduced-motion` block does not cover this.** That
 * rule zeroes CSS `animation-duration`/`transition-duration`, and framer-motion
 * drives transforms via inline styles and the Web Animations API — a
 * different mechanism the CSS rule cannot see. `TranscriptPanel` already hit
 * this exact gap for `scrollIntoView` and solved it by checking the media
 * query directly; `useReducedMotion` is the same fix for this library.
 *
 * `viewport={{ once: true }}` — a card that re-animates every time it
 * scrolls back into view reads as broken, not delightful, on a page anyone
 * scrolls up on.
 */
const variants: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0 },
};

export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) return <div className={className}>{children}</div>;

  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-40px" }}
      variants={variants}
      transition={{ duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
