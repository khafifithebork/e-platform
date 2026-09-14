import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, letting a later Tailwind utility win over an earlier
 * conflicting one.
 *
 * `clsx` collects conditionals (`cn("a", cond && "b")`); `twMerge` then
 * resolves same-property collisions by source order rather than leaving both
 * in the string, which is what makes `className` overrides from a caller
 * (`cn(base, className)`) actually take effect instead of losing a specificity
 * fight to whichever utility happens to come first in the generated stylesheet.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
