"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { buttonStyles } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { sessionStatus } from "@/lib/auth/session-status";

/** Response-driven feedback: no focus transfer, redirect, timer or animation. */
export function SessionExpiryNotice() {
  const session = useSyncExternalStore(sessionStatus.subscribe, sessionStatus.getSnapshot, sessionStatus.getServerSnapshot);
  if (session.status !== "ended") return null;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col items-start gap-3 px-6 py-5 sm:flex-row sm:items-center">
      <div className="min-w-0 w-full flex-1 [overflow-wrap:anywhere]">
        <Notice tone="error" title="Sign in to continue">{session.detail}</Notice>
      </div>
      <Link href="/login" className={buttonStyles({ variant: "secondary", lift: false, className: "shrink-0" })}>
        Sign in
      </Link>
    </div>
  );
}
