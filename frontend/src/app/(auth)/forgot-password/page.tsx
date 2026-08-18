"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError, api } from "@/lib/api/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    setFieldErrors({});

    try {
      await api.requestPasswordReset(email);
      setSubmitted(true);
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

  // Same reasoning as registration: the wording holds whether or not an
  // account exists, because the API refuses to say which.
  if (submitted) {
    return (
      <>
        <h1 className="font-display text-3xl tracking-tight text-ink">
          Check your inbox
        </h1>
        <div className="mt-6">
          <Notice tone="success" title="Sent, if we could">
            If <span className="font-medium">{email}</span> has an account, a
            reset link is on its way. It expires in one hour.
          </Notice>
        </div>
        <p className="mt-6 text-sm text-ink-muted">
          <Link href="/login" className="text-accent underline underline-offset-4">
            Back to sign in
          </Link>
        </p>
      </>
    );
  }

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight text-ink">
        Reset your password
      </h1>
      <p className="mt-2 text-ink-muted">
        We will email you a link to set a new one.
      </p>

      <form onSubmit={handleSubmit} noValidate className="mt-8 flex flex-col gap-5">
        {problem && <Notice tone="error">{problem}</Notice>}

        <Field
          label="Email"
          name="email"
          type="email"
          value={email}
          onChange={setEmail}
          errors={fieldErrors.email}
          autoComplete="email"
          required
          disabled={pending}
        />

        <Button type="submit" pending={pending} pendingLabel="Sending…">
          Send reset link
        </Button>
      </form>

      <p className="mt-6 text-sm">
        <Link
          href="/login"
          className="text-ink-muted underline underline-offset-4 hover:text-ink"
        >
          Back to sign in
        </Link>
      </p>
    </>
  );
}
