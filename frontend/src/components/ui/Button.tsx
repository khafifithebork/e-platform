import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  /** Shows progress and blocks repeat submits. */
  pending?: boolean;
  pendingLabel?: string;
}

const VARIANTS = {
  primary:
    "bg-accent text-on-accent hover:bg-accent-hover disabled:hover:bg-accent",
  secondary:
    "bg-surface text-ink border border-line-strong hover:border-ink-subtle",
} as const;

export function Button({
  variant = "primary",
  pending = false,
  pendingLabel = "Working…",
  children,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || pending}
      // aria-busy rather than swapping in a spinner alone: a screen reader
      // should know the control is working, not just that its label changed.
      aria-busy={pending}
      className={`inline-flex items-center justify-center rounded-[--radius-sm]
        px-4 py-2 text-sm font-medium transition-colors
        disabled:cursor-not-allowed disabled:opacity-60
        ${VARIANTS[variant]} ${className}`}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
