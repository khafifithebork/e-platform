"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { motion } from "framer-motion";
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
  /*
   * No `text-sm` here. Each size owns its type size instead, because the base
   * and a size both setting one only works for callers that run the result
   * through `tailwind-merge` — `Button` does, and the links that compose
   * `buttonStyles` do not. Measured: with `text-sm` in the base, `size: "lg"`
   * produced 14px text because CSS order decided it, silently shrinking the
   * landing page's calls to action from 16px while every test stayed green.
   */
  /*
   * `border border-transparent` in the base, overridden by `secondary`.
   *
   * Without it a bordered variant is 2px taller than an unbordered one at the
   * same size, and `min-h-11` does not save you: a minimum is a floor, not a cap.
   * Measured both ways on the landing page's two calls to action — at `text-sm`
   * the floor was binding for both so they happened to match at 44px, and at
   * `text-base` the content grew past it and they came out 44 and 46, visibly
   * misaligned side by side. A transparent border makes every variant the same
   * box whatever the type size, which is the property actually wanted.
   */
  `inline-flex items-center justify-center gap-2 rounded-(--radius-md)
   border border-transparent font-medium
   transition-[color,background-color,border-color,box-shadow]
   duration-150 disabled:cursor-not-allowed disabled:opacity-60`,
  {
    variants: {
      variant: {
        primary: `bg-accent text-on-accent shadow-(--shadow-sm)
          hover:bg-accent-hover
          disabled:hover:bg-accent disabled:hover:shadow-(--shadow-sm)`,
        secondary: `border-line-strong bg-surface text-ink
          hover:border-ink-subtle hover:bg-surface-sunken`,
        ghost: `text-ink-muted hover:bg-surface-sunken hover:text-ink`,
      },
      size: {
        /** A page's main call to action, at body size rather than control size. */
        lg: "min-h-11 px-5 py-2.5 text-base",
        md: "min-h-11 px-5 py-2.5 text-sm",
        sm: "min-h-10 px-3.5 py-2 text-[0.8125rem]",
      },
      /**
       * Raises the shadow on hover. Off for `<button>`s and on for the
       * link-shaped calls to action, which is how they were already written —
       * see `buttonStyles` below for why that difference is preserved rather
       * than settled here.
       */
      lift: {
        true: "hover:shadow-(--shadow-md)",
        false: "",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
      lift: false,
    },
  },
);

/**
 * The same styling, for the links that are calls to action rather than buttons.
 *
 * **Five `<a>` elements were reimplementing this by hand** — both hero CTAs, both
 * on the 404, and the resume link on an enrolment card — and they had drifted
 * from each other and from this file in four ways: three different
 * `transition-*` values, two paddings, no `min-height` at all, and no shared
 * definition to drift back towards.
 *
 * **The defect that made this worth doing is measurable rather than aesthetic.**
 * On the landing page the two CTAs sat side by side at 44px and 46px: the
 * secondary carries a border, neither set a height, and `box-sizing: border-box`
 * cannot help when nothing constrains the box. `min-h-11` on both settles it at
 * 44px — which is also the touch target this file already wanted, and which the
 * enrolment card's 36px link was quietly missing.
 *
 * A link is not a button and does not take this component: it needs an `href`,
 * it is not disableable, and `whileTap` on a navigation is the wrong gesture. So
 * the styles are exported and the links compose them, the same arrangement
 * `PAGE_TITLE` uses for the one heading that cannot be a `PageTitle`.
 *
 * **Two differences are deliberately preserved rather than resolved**, because
 * both are design decisions and neither is a bug: the CTAs are `text-base` where
 * a `<button>` is `text-sm` (hence `size: "lg"`), and they raise their shadow on
 * hover where a `<button>` holds still (hence `lift`). Unifying either one would
 * change how the product looks, which is not a call to make while fixing an
 * alignment bug.
 */
export const buttonStyles = button;

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
      // released on up. Skipped when the control cannot be pressed at all —
      // animating a scale on a disabled button would be motion with nothing
      // for it to mean. Reduced motion is no longer decided here: `whileTap`
      // makes Motion add a `tabindex`, so branching on it during render
      // changed the markup and mismatched hydration. `MotionProvider`
      // disables the scale instead, after the tree is identical.
      whileTap={!isDisabled ? { scale: 0.97 } : undefined}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
    >
      {pending ? pendingLabel : children}
    </motion.button>
  );
}
