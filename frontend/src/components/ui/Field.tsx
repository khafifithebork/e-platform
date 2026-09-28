import { useId } from "react";

interface FieldProps {
  label: string;
  type?: "text" | "email" | "password";
  name: string;
  value: string;
  onChange: (value: string) => void;
  /** Server-side field errors, straight from the Problem Details `errors` map. */
  errors?: string[];
  hint?: string;
  autoComplete?: string;
  required?: boolean;
  disabled?: boolean;
}

/**
 * A labelled input with its errors and hint wired up for assistive technology.
 *
 * The wiring is the point. A visible red border tells a sighted user something
 * is wrong and tells a screen-reader user nothing, so the message is linked by
 * `aria-describedby` and the field is marked `aria-invalid`. Errors are also
 * announced via `role="alert"`, because they appear after the user has already
 * moved on from the field.
 */
export function Field({
  label,
  type = "text",
  name,
  value,
  onChange,
  errors,
  hint,
  autoComplete,
  required,
  disabled,
}: FieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const hasErrors = Boolean(errors?.length);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {!required && <span className="ms-1.5 text-ink-subtle">(optional)</span>}
      </label>

      {hint && (
        <p id={hintId} className="text-sm text-ink-muted">
          {hint}
        </p>
      )}

      <input
        id={id}
        name={name}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        required={required}
        disabled={disabled}
        aria-invalid={hasErrors}
        aria-describedby={
          [hasErrors ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") ||
          undefined
        }
        className={`rounded-(--radius-md) border bg-surface px-3.5 py-2.5 text-ink
          shadow-(--shadow-sm) transition-colors placeholder:text-ink-subtle
          disabled:cursor-not-allowed disabled:opacity-60
          ${hasErrors ? "border-danger" : "border-line-strong hover:border-ink-subtle"}`}
      />

      {/*
       * `role="alert"` on a wrapper, not on the `<ul>` itself.
       *
       * **It used to be on the list, and that quietly destroyed the list.** An
       * explicit role *replaces* an element's implicit one, so `role="alert"` on a
       * `<ul>` leaves it announcing as an alert and no longer as a list — while
       * still containing `<li>` children with no list to belong to. Assistive
       * technology is then free to ignore them or announce them without position
       * or count.
       *
       * Found by axe on the first run after it was adopted (§5, 2026-09-28), as
       * two violations: `aria-allowed-role` and `listitem`. Neither the structural
       * greps nor `Field.test.tsx` could see it — the test asserted that a
       * `role="alert"` element exists and contains the message, which was true
       * both before and after.
       *
       * The live region still does its job on the wrapper: an alert announces its
       * content when it appears, which is the point — errors arrive after the user
       * has moved on from the field.
       */}
      {hasErrors && (
        <div id={errorId} role="alert">
          <ul className="flex flex-col gap-1">
            {errors?.map((message) => (
              <li key={message} className="text-sm text-danger">
                {message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
