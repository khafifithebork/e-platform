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
        {!required && <span className="ml-1.5 text-ink-subtle">(optional)</span>}
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
        className={`rounded-[--radius-sm] border bg-surface px-3 py-2 text-ink
          transition-colors placeholder:text-ink-subtle
          disabled:cursor-not-allowed disabled:opacity-60
          ${hasErrors ? "border-danger" : "border-line-strong hover:border-ink-subtle"}`}
      />

      {hasErrors && (
        <ul id={errorId} role="alert" className="flex flex-col gap-1">
          {errors?.map((message) => (
            <li key={message} className="text-sm text-danger">
              {message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
