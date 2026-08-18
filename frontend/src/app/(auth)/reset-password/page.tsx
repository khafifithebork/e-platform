"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError, api } from "@/lib/api/client";

function ResetPasswordForm() {
  // The token arrives in the emailed link. It is never rendered into the page
  // and never stored — it goes straight back to the API and is consumed.
  const token = useSearchParams().get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    setFieldErrors({});

    try {
      await api.confirmPasswordReset(token, newPassword);
      setDone(true);
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

  if (!token) {
    return (
      <>
        <h1 className="font-display text-3xl tracking-tight text-ink">
          This link is incomplete
        </h1>
        <div className="mt-6">
          <Notice tone="error">
            The reset link is missing its token. Links can be truncated by email
            clients — try copying the whole address, or request a new one.
          </Notice>
        </div>
        <p className="mt-6 text-sm">
          <Link
            href="/forgot-password"
            className="text-accent underline underline-offset-4"
          >
            Request a new link
          </Link>
        </p>
      </>
    );
  }

  if (done) {
    return (
      <>
        <h1 className="font-display text-3xl tracking-tight text-ink">
          Password changed
        </h1>
        <div className="mt-6">
          <Notice tone="success" title="You are signed out everywhere">
            Any other device that was signed in has been signed out. Sign in
            again with your new password.
          </Notice>
        </div>
        <p className="mt-6">
          <Link href="/login" className="text-accent underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </>
    );
  }

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight text-ink">
        Choose a new password
      </h1>

      <form onSubmit={handleSubmit} noValidate className="mt-8 flex flex-col gap-5">
        {problem && <Notice tone="error">{problem}</Notice>}

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
          Set new password
        </Button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams needs a Suspense boundary, or the whole route opts out of
  // static rendering.
  return (
    <Suspense fallback={<p className="text-ink-muted">Loading…</p>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
