"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageTitle } from "@/components/ui/PageTitle";
import { ApiError, api } from "@/lib/api/client";

function ResetPasswordForm() {
  /**
   * The token, from the query string if a link carried one.
   *
   * **It is never rendered into the page and never stored** — it goes straight
   * back to the API and is consumed. `page.test.tsx` asserts that, including
   * against an attribute, and it is why a token from the URL is *not* prefilled
   * into the field below: putting it in an input would put it in the DOM.
   */
  const linkToken = useSearchParams().get("token") ?? "";

  /**
   * A token the person typed, for when no link carried one.
   *
   * **The emails send a bare token, not a link** — see
   * `backend/apps/notifications/templates/email/password_reset/body.txt`. Until
   * 2026-09-28 this page refused any visit without `?token=`, which meant the
   * token every reset email actually sends could not be redeemed anywhere: there
   * was nothing to paste it into. This is that field.
   *
   * Separate state from `linkToken` on purpose. A pasted value is visible because
   * the person typed it, which is fine; a value taken from the URL and echoed into
   * an input would be us rendering it, which the assertion above forbids.
   */
  const [pastedToken, setPastedToken] = useState("");
  const token = linkToken || pastedToken;

  const [newPassword, setNewPassword] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setProblem(null);
    setFieldErrors({});

    if (!token) {
      // Refused here rather than posted. An empty token cannot succeed — the
      // service short-circuits it — so sending one spends a rate-limit slot on
      // a certain failure and answers with a message about a token instead of
      // about the empty field in front of them.
      setFieldErrors({ token: ["Paste the token from the email."] });
      return;
    }

    setPending(true);

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

  if (done) {
    return (
      <>
        <PageTitle variant="interstitial">
          Password changed
        </PageTitle>
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
      <PageTitle variant="interstitial">
        Choose a new password
      </PageTitle>

      {!linkToken && (
        <p className="mt-2 text-ink-muted">
          Paste the token from the password reset email, then choose the new
          password.
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate className="mt-8 flex flex-col gap-5">
        {problem && <Notice tone="error">{problem}</Notice>}

        {/*
         * Only when the URL did not carry one. On the link path this field would
         * have to be prefilled to be useful, and prefilling it would put the
         * token in the DOM — the one thing `page.test.tsx` forbids.
         */}
        {!linkToken && (
          <Field
            label="Reset token"
            name="token"
            value={pastedToken}
            onChange={setPastedToken}
            errors={fieldErrors.token}
            hint="From the email. It expires one hour after it was sent."
            autoComplete="off"
            required
            disabled={pending}
          />
        )}

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

      {/* Shown on both paths. A token that has expired is the common case on the
          link path too, and the way out of it is another email. */}
      <p className="mt-6 text-sm">
        <Link
          href="/forgot-password"
          className="text-ink-muted underline underline-offset-4 hover:text-ink"
        >
          Request a new token
        </Link>
      </p>
    </>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams needs a Suspense boundary, or the whole route opts out of
  // static rendering.
  return (
    <Suspense
      fallback={
        // The fallback carries the heading, not just a spinner word.
        //
        // `useSearchParams` forces this subtree to render on the client, so
        // **this is the entire prerendered page** — and until M15 T10 it was
        // the word "Loading…" alone, giving the statically served document no
        // `<h1>` at all. A page with no heading has no title in the heading
        // outline, which is how a screen-reader user establishes where they
        // are before anything has hydrated.
        <>
          <PageTitle variant="interstitial">
            Choose a new password
          </PageTitle>
          <p className="mt-6 text-ink-muted">Loading…</p>
        </>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
