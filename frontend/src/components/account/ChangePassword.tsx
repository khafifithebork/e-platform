"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError, api } from "@/lib/api/client";

/**
 * Changing your password while signed in.
 *
 * **`POST /auth/password/change/` had no caller until 2026-09-29.** It is the only
 * authenticated endpoint in the auth group and it has existed since M2; without a
 * form, the only way to change a password was to sign out and use the emailed reset,
 * which needs an inbox and is a worse flow for somebody already signed in.
 *
 * **The copy differs from the reset page's on purpose.** `PasswordChangeView` calls
 * `update_session_auth_hash` after the change, so *this* browser stays signed in
 * while every other session dies. The reset page says "You are signed out
 * everywhere", which is true there and false here — borrowing it would tell somebody
 * they are about to be signed out of the tab they are looking at.
 *
 * The refusal is the API's own sentence, not ours. The backend answers *"Your
 * current password is not correct."* for a wrong current password and a field error
 * for a weak new one; inventing wording here would eventually disagree with it.
 */
export function ChangePassword() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const [changed, setChanged] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    setFieldErrors({});

    try {
      await api.changePassword(currentPassword, newPassword);
      setChanged(true);
      // Cleared on success, not in `finally`: after a refusal the fields keep
      // what was typed so somebody correcting one character does not retype both.
      setCurrentPassword("");
      setNewPassword("");
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fieldErrors);
        setProblem(error.problem.detail);
      } else {
        setProblem("Could not reach the server. Check your connection.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="password" className="flex flex-col gap-4">
      <h2 id="password" className="font-display text-2xl text-ink">
        Password
      </h2>

      <div className="flex min-w-0 flex-col gap-5 border-t border-line pt-5 [overflow-wrap:anywhere]">
        {changed ? (
          <Notice tone="success" title="Password changed">
            Your other devices have been signed out. This one stays signed in.
          </Notice>
        ) : null}

        <form onSubmit={handleSubmit} noValidate className="flex w-full max-w-sm flex-col gap-5">
          {problem && <Notice tone="error">{problem}</Notice>}

          <Field
            label="Current password"
            name="current_password"
            type="password"
            value={currentPassword}
            onChange={setCurrentPassword}
            errors={fieldErrors.current_password}
            autoComplete="current-password"
            required
            disabled={pending}
          />

          <Field
            label="New password"
            name="new_password"
            type="password"
            value={newPassword}
            onChange={setNewPassword}
            errors={fieldErrors.new_password}
            hint="At least 8 characters, and not a password everyone else uses."
            autoComplete="new-password"
            required
            disabled={pending}
          />

          <Button type="submit" pending={pending} pendingLabel="Saving…">
            Change password
          </Button>
        </form>
      </div>
    </section>
  );
}
