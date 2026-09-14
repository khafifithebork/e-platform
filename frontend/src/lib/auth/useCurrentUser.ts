"use client";

import { useEffect, useState } from "react";

import { ApiError, api, type Me } from "@/lib/api/client";

/**
 * Who is signed in, resolved in the browser.
 *
 * Same three-state shape and the same reasoning `AuthMenu` documents at
 * length: it starts `unknown` rather than guessing `anonymous`, because a
 * guess that is wrong reads as "you have been signed out" to every subscriber
 * on every page load. A 403 from `/auth/me/` is the answer "nobody", not a
 * failure.
 *
 * **Extracted for `SiteNavTree`, not folded into `AuthMenu` itself.**
 * `AuthMenu` predates this hook and is tested standalone with no provider —
 * rewiring it to share one request across two consumers would mean either
 * breaking those tests or adding a context provider two call sites don't
 * otherwise need. A second `/auth/me/` request is cheap; refactoring
 * working, documented, tested code to avoid it is not worth the risk here.
 */
export type AuthState = { status: "unknown" } | { status: "anonymous" } | { status: "signed-in"; me: Me };

export function useCurrentUser(): AuthState {
  const [state, setState] = useState<AuthState>({ status: "unknown" });

  useEffect(() => {
    let current = true;

    api
      .me()
      .then((me) => {
        if (current) setState({ status: "signed-in", me });
      })
      .catch((error: unknown) => {
        if (!current) return;

        setState({ status: "anonymous" });
        if (!(error instanceof ApiError)) {
          console.debug("Could not resolve the session", error);
        }
      });

    return () => {
      current = false;
    };
  }, []);

  return state;
}
