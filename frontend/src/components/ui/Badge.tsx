import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

/**
 * The small pill this app already drew four times: a skill tag, a CEFR level,
 * "Free preview". Each site had its own copy of the same three utilities —
 * `rounded-[--radius-sm] bg-surface-sunken px-2 py-0.5 text-xs` — with the
 * accent variant only on the one badge that meant something ("Free preview"
 * is the one badge a visitor might act on; a skill tag is not). One
 * component makes that distinction a prop instead of a thing to notice by
 * diffing two `<span>`s.
 */
const badge = cva("inline-flex items-center rounded-[--radius-sm] px-2 py-0.5 text-xs font-medium", {
  variants: {
    tone: {
      neutral: "bg-surface-sunken text-ink-muted",
      accent: "bg-accent-subtle text-accent",
    },
  },
  defaultVariants: {
    tone: "neutral",
  },
});

export function Badge({
  tone,
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}
