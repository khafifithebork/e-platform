"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError, api } from "@/lib/api/client";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      await api.register(email, password);
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

  /*
   * The confirmation deliberately does not say whether an account was created.
   *
   * The API answers identically whether the address was free or already taken,
   * so that someone cannot test a list of addresses against this form. A
   * cheerful "check your inbox!" is the right words for both outcomes; "we
   * sent you an email" would be a lie in one of them.
   */
  if (submitted) {
    return (
      <>
        <h1 className="font-display text-3xl tracking-tight text-ink">
          Check your inbox
        </h1>
        <div className="mt-6">
          <Notice tone="success" title="Almost there">
            If <span className="font-medium">{email}</span> can be registered,
            a verification link is on its way. It expires in 24 hours.
          </Notice>
        </div>
        <p className="mt-6 text-sm text-ink-muted">
          Already verified?{" "}
          <Link href="/login" className="text-accent underline underline-offset-4">
            Sign in
          </Link>
          .
        </p>
      </>
    );
  }

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight text-ink">
        Create an account
      </h1>
      <p className="mt-2 text-ink-muted">
        Already have one?{" "}
        <Link href="/login" className="text-accent underline underline-offset-4">
          Sign in
        </Link>
        .
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

        <Field
          label="Password"
          name="password"
          type="password"
          value={password}
          onChange={setPassword}
          errors={fieldErrors.password}
          hint="At least 8 characters, and not a password everyone else uses."
          autoComplete="new-password"
          required
          disabled={pending}
        />

        <Button type="submit" pending={pending} pendingLabel="Creating…">
          Create account
        </Button>
      </form>
    </>
  );
}
