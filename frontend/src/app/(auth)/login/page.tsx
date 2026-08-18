"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError, api } from "@/lib/api/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    setFieldErrors({});

    try {
      await api.login(email, password);
      router.push("/");
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fieldErrors);
        // The API answers identically for a wrong password, an unknown
        // address and a locked account. Echoing its message verbatim is what
        // keeps that true — inventing a friendlier one here would leak the
        // distinction the backend went to trouble to hide.
        setProblem(error.problem.detail);
      } else {
        setProblem("Could not reach the server. Check your connection.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight text-ink">Sign in</h1>
      <p className="mt-2 text-ink-muted">
        New here?{" "}
        <Link href="/register" className="text-accent underline underline-offset-4">
          Create an account
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
          autoComplete="current-password"
          required
          disabled={pending}
        />

        <Button type="submit" pending={pending} pendingLabel="Signing in…">
          Sign in
        </Button>
      </form>

      <p className="mt-6 text-sm">
        <Link
          href="/forgot-password"
          className="text-ink-muted underline underline-offset-4 hover:text-ink"
        >
          Forgotten your password?
        </Link>
      </p>
    </>
  );
}
