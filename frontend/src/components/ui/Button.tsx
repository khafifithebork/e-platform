"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { motion, useReducedMotion } from "framer-motion";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

/**
 * Variants as data, not as a chain of ternaries in the JSX.
 *
 * `cva` is the one piece of the shadcn/ui toolchain this app actually needed —
 * Radix primitives are not, because nothing here is a dialog, a menu or a tab
 * strip. Adding `@radix-ui/*` packages with no component to import them into
 * would be exactly the unused dependency CLAUDE.md §5 exists to keep out; this
 * is the useful half without the unused rest.
 */
/*
 * No `focus-visible:outline-none` here. `globals.css` gives every focusable
 * element a visible ring via `:where(...)`, which is written at zero
 * specificity on purpose — but a plain `outline: none` from a utility class
 * on the button itself would still win regardless of source order, because
 * `:where()`'s zero specificity only loses, never ties. Suppressing it here
 * "to replace it with something nicer" is how a button quietly stops showing
 * where keyboard focus is.
 */
const button = cva(
  `inline-flex items-center justify-center gap-2 rounded-[--radius-sm]
   text-sm font-medium transition-colors duration-150
   disabled:cursor-not-allowed disabled:opacity-60`,
  {
    variants: {
      variant: {
        primary: `bg-accent text-on-accent shadow-[--shadow-sm]
          hover:bg-accent-hover hover:shadow-[--shadow-md]
          disabled:hover:bg-accent disabled:hover:shadow-[--shadow-sm]`,
        secondary: `border border-line-strong bg-surface text-ink
          hover:border-ink-subtle hover:bg-surface-sunken`,
        ghost: `text-ink-muted hover:bg-surface-sunken hover:text-ink`,
      },
      size: {
        md: "px-4 py-2",
        sm: "px-3 py-1.5 text-[0.8125rem]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

/**
 * See `Card.tsx` for why these three are excluded: React's native DOM
 * events and framer-motion's animation/gesture props share five names with
 * incompatible signatures, and nothing here uses any of them.
 */
type ButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd"
> &
  VariantProps<typeof button> & {
    /** Shows progress and blocks repeat submits. */
    pending?: boolean;
    pendingLabel?: string;
  };

export function Button({
  variant,
  size,
  pending = false,
  pendingLabel = "Working…",
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const reduceMotion = useReducedMotion();
  const isDisabled = disabled || pending;

  return (
    <motion.button
      {...props}
      disabled={isDisabled}
      // aria-busy rather than swapping in a spinner alone: a screen reader
      // should know the control is working, not just that its label changed.
      aria-busy={pending}
      className={cn(button({ variant, size }), className)}
      // A press should read as a press: a slight compression on pointer-down,
      // released on up. Skipped when reduced motion is requested or the
      // control cannot be pressed at all — animating a scale on a disabled
      // button would be motion with nothing for it to mean.
      whileTap={!reduceMotion && !isDisabled ? { scale: 0.97 } : undefined}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
    >
      {pending ? pendingLabel : children}
    </motion.button>
  );
}
