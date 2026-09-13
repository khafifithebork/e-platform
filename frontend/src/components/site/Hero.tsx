"use client";

import { motion, useReducedMotion, useScroll, useTransform, type Variants } from "framer-motion";
import Link from "next/link";
import { useRef } from "react";

const containerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.05 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] } },
};

/**
 * The landing page's opening section: headline, the two real CTAs, and a
 * decorative stack of cards standing in for the catalogue.
 *
 * **A client component, carved out of an otherwise server-rendered page.**
 * `Home` stays `async`, fetches at build time, and remains statically
 * generated (invariant 15) — only the part that needs mount-triggered motion
 * and scroll position crosses the client boundary, the same split `AuthMenu`
 * and `CourseProgress` already use for their own reasons.
 *
 * **Animates on mount, not on scroll into view.** `Reveal` exists for
 * below-the-fold sections a visitor scrolls to; this is the first thing
 * anyone sees, so it enters immediately rather than waiting for an
 * intersection that has already happened.
 *
 * The three-card stack behind the copy is decorative — `aria-hidden` — and
 * deliberately not an illustration of anything. It stands for "a catalogue",
 * the way three overlapping cards do in most course-marketplace hero
 * sections, without claiming to depict a specific course that does not exist
 * (§6 forbids inventing content, and a screenshot-shaped mock would read as
 * one).
 */
export function Hero() {
  const reduceMotion = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);

  // The background glow drifts slightly slower than the page scrolls — a
  // parallax of a few percent, not a full effect. `useScroll`'s target is
  // this section itself, so the range is "while the hero is on screen",
  // not the whole document.
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start start", "end start"] });
  const glowY = useTransform(scrollYProgress, [0, 1], ["0%", "30%"]);

  const container = reduceMotion
    ? {}
    : { initial: "hidden" as const, animate: "visible" as const, variants: containerVariants };

  const item = reduceMotion ? {} : { variants: itemVariants };

  return (
    <section ref={sectionRef} className="relative overflow-hidden">
      <motion.div
        aria-hidden="true"
        style={reduceMotion ? undefined : { y: glowY }}
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[36rem]
          bg-[radial-gradient(ellipse_60%_50%_at_50%_-10%,var(--color-accent-subtle),transparent)]"
      />

      <div className="mx-auto grid max-w-5xl gap-12 px-6 pt-20 lg:grid-cols-[3fr_2fr] lg:items-center">
        <motion.div className="flex max-w-2xl flex-col gap-6" {...container}>
          <motion.h1
            {...item}
            className="font-display text-4xl leading-tight tracking-tight text-ink sm:text-5xl"
          >
            Language courses, reviewed before they are published.
          </motion.h1>

          <motion.p {...item} className="text-lg leading-relaxed text-ink-muted">
            Every course here was submitted by an instructor and approved by a
            person before anyone could see it. No open marketplace, no
            auto-published backlog.
          </motion.p>

          <motion.div {...item} className="flex flex-col gap-3 sm:flex-row">
            <motion.div whileTap={reduceMotion ? undefined : { scale: 0.97 }}>
              <Link
                href="/courses"
                className="block rounded-[--radius-md] bg-accent px-5 py-2.5 text-center
                  font-medium text-on-accent shadow-[--shadow-sm] transition-shadow
                  hover:bg-accent-hover hover:shadow-[--shadow-md]"
              >
                Browse the catalogue
              </Link>
            </motion.div>
            <motion.div whileTap={reduceMotion ? undefined : { scale: 0.97 }}>
              <Link
                href="/pricing"
                className="block rounded-[--radius-md] border border-line-strong bg-surface
                  px-5 py-2.5 text-center font-medium text-ink transition-colors
                  hover:border-ink-subtle hover:bg-surface-sunken"
              >
                See pricing
              </Link>
            </motion.div>
          </motion.div>
        </motion.div>

        {/* The card stack. Hidden below `lg`: three rotated cards beside
            already-tight copy on a phone screen is clutter, not depth. */}
        <div aria-hidden="true" className="relative hidden h-64 lg:block">
          <motion.div
            initial={reduceMotion ? undefined : { opacity: 0, y: 30, rotate: -6 }}
            animate={{ opacity: 1, y: 0, rotate: -6 }}
            transition={{ duration: 0.6, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="absolute left-8 top-6 h-40 w-56 rounded-[--radius-lg] border
              border-line bg-surface-sunken shadow-[--shadow-sm]"
          />
          <motion.div
            initial={reduceMotion ? undefined : { opacity: 0, y: 30, rotate: 4 }}
            animate={{ opacity: 1, y: 0, rotate: 4 }}
            transition={{ duration: 0.6, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="absolute right-4 top-2 h-40 w-56 rounded-[--radius-lg] border
              border-line bg-surface shadow-[--shadow-md]"
          />
          <motion.div
            initial={reduceMotion ? undefined : { opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="absolute inset-x-10 bottom-0 flex h-40 w-56 flex-col justify-between
              rounded-[--radius-lg] border border-line-strong bg-surface p-5 shadow-[--shadow-md]"
          >
            <div className="h-2.5 w-16 rounded-full bg-accent" />
            <div className="flex flex-col gap-1.5">
              <div className="h-2 w-full rounded-full bg-line" />
              <div className="h-2 w-3/4 rounded-full bg-line" />
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
