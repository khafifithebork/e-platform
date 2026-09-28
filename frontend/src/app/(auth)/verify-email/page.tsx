"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageTitle } from "@/components/ui/PageTitle";
import { ApiError, api } from "@/lib/api/client";

/**
 * Redeeming an email verification token.
 *
 * **This page did not exist until 2026-09-28, and `POST /auth/verify-email/` had
 * no caller.** Registration issues a token and emails it; the email
 * (`backend/apps/notifications/templates/email/verification/body.txt`) sends the
 * token as bare text with no URL, because there is no configured site URL to
 * build one from. So the token was unredeemable: the endpoint existed, the client
 * wrapper existed, and there was nowhere to put the thing the email sent.
 *
 * Two deliberate shapes here, both explained where they are:
 *
 * 1. A token from `?token=` is held in state and never rendered, matching
 *    `reset-password`. A pasted one is visible because the person typed it.
 * 2. Verification happens on a click, never on mount. See `handleVerify`.
 */

function VerifyEmailForm() {
  /**
   * The token, if a link carried one — never rendered, never stored.
   *
   * Same property as `reset-password`, asserted the same way in `page.test.tsx`:
   * a URL is the one place a secret in this app is visible, so echoing it into an
   * input or an attribute widens the window in which it can be shoulder-read,
   * screenshotted, or read by an extension.
   */
  const linkToken = useSearchParams().get("token") ?? "";

  /** A token the person pasted, for the bare-token email that is what we send. */
  const [pastedToken, setPastedToken] = useState("");
  const token = linkToken || pastedToken;

  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const [verified, setVerified] = useState(false);

  /**
   * Verify on a click, not in an effect on mount.
   *
   * Auto-verifying would read as the obvious thing for a link, and it is wrong
   * twice over. A verification token is single-use, so any second POST for the
   * same token fails — which means React's double-invoked effects in development,
   * a refresh, or a back-navigation all show "not valid" on a token that
   * verified perfectly. And since the email sends no link today, the click costs
   * a person nothing they were not already doing.
   */
  async function handleVerify(event: React.FormEvent) {
    event.preventDefault();
    setProblem(null);
    setFieldErrors({});

    if (!token) {
      // Not posted. An empty token cannot succeed — `verify_email` short-circuits
      // it precisely so that an empty digest cannot match a stored row — so
      // sending one spends a rate-limit slot on a certain failure.
      setFieldErrors({ token: ["Paste the token from the email."] });
      return;
    }

    setPending(true);

    try {
      await api.verifyEmail(token);
      setVerified(true);
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

  if (verified) {
    return (
      <>
        <PageTitle variant="interstitial">
          Email address verified
        </PageTitle>
        <div className="mt-6">
          <Notice tone="success" title="That is done">
            Your address is confirmed. Sign in to carry on.
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
        Verify your email address
      </PageTitle>
      <p className="mt-2 text-ink-muted">
        {linkToken
          ? "Confirm below and your address is verified."
          : "Paste the token from the verification email."}
      </p>

      <form onSubmit={handleVerify} noValidate className="mt-8 flex flex-col gap-5">
        {problem && <Notice tone="error">{problem}</Notice>}

        {/* Only when the URL did not carry one; prefilling it would put the token
            in the DOM, which is the property above. */}
        {!linkToken && (
          <Field
            label="Verification token"
            name="token"
            value={pastedToken}
            onChange={setPastedToken}
            errors={fieldErrors.token}
            hint="From the email. It expires 24 hours after it was sent."
            autoComplete="off"
            required
            disabled={pending}
          />
        )}

        <Button type="submit" pending={pending} pendingLabel="Verifying…">
          Verify my address
        </Button>
      </form>

      <ResendVerification />
    </>
  );
}

/**
 * A fresh token, for the expired and the lost.
 *
 * On the page rather than a route of its own because it is the only way out of a
 * failed verification, and a dead end is the defect this page was added to fix.
 *
 * **The confirmation must hold for three outcomes it cannot tell apart.**
 * `ResendVerificationView` answers 202 identically for an unknown address, an
 * already-verified one, and a genuine resend — deliberately, so the form is not
 * a way to test a list of addresses against the user table. The wording is
 * therefore conditional, as on `register` and `forgot-password`, and
 * `page.test.tsx` pins it the same way: by rendering two different addresses and
 * requiring the markup to come out byte-identical.
 */
function ResendVerification() {
  const [email, setEmail] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleResend(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    setFieldErrors({});

    try {
      await api.resendVerification(email);
      setSent(true);
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
    <section className="mt-10 border-t border-line pt-8">
      <h2 className="text-sm font-medium text-ink">Lost or expired token?</h2>

      {sent ? (
        <div className="mt-4">
          <Notice tone="success" title="Sent, if we could">
            If <span className="font-medium">{email}</span> has an unverified
            account, a new token is on its way. It expires in 24 hours.
          </Notice>
        </div>
      ) : (
        <form onSubmit={handleResend} noValidate className="mt-4 flex flex-col gap-4">
          {problem && <Notice tone="error">{problem}</Notice>}

          <Field
            label="Email"
            name="resend_email"
            type="email"
            value={email}
            onChange={setEmail}
            errors={fieldErrors.email}
            autoComplete="email"
            required
            disabled={pending}
          />

          <Button type="submit" variant="secondary" pending={pending} pendingLabel="Sending…">
            Send a new token
          </Button>
        </form>
      )}
    </section>
  );
}

export default function VerifyEmailPage() {
  // `useSearchParams` needs a Suspense boundary, or the whole route opts out of
  // static rendering — and the fallback carries the `<h1>`, because with the form
  // on the client the fallback *is* the prerendered document. Same reasoning as
  // `reset-password`, where the bare word "Loading…" was the whole static page.
  return (
    <Suspense
      fallback={
        <>
          <PageTitle variant="interstitial">
            Verify your email address
          </PageTitle>
          <p className="mt-6 text-ink-muted">Loading…</p>
        </>
      }
    >
      <VerifyEmailForm />
    </Suspense>
  );
}
