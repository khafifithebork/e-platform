"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { ApiError, api, type Me } from "@/lib/api/client";
import { sessionStatus } from "./session-status";

/** Browser-resolved identity for the header and navigation; never persisted. */
export type AuthState = { status: "unknown" } | { status: "anonymous" } | { status: "signed-in"; me: Me };

export function useCurrentUser(): AuthState {
  const [state, setState] = useState<AuthState>({ status: "unknown" });
  const observation = useSyncExternalStore(sessionStatus.subscribe, sessionStatus.getSnapshot, sessionStatus.getServerSnapshot);

  useEffect(() => {
    let current = true;
    let generation = 0;
    let ended = sessionStatus.getSnapshot().status === "ended";

    function resolveIdentity() {
      const requestGeneration = ++generation;
      api.me().then((me) => {
        if (current) {
          if (requestGeneration === generation) setState({ status: "signed-in", me });
        }
      }).catch((error: unknown) => {
        if (!current || requestGeneration !== generation) return;
        // An unresolved header offers a way in; it does not surface network errors.
        setState({ status: "anonymous" });
        if (!(error instanceof ApiError)) console.debug("Could not resolve the session", error);
      });
    }

    const unsubscribe = sessionStatus.subscribe(() => {
      const next = sessionStatus.getSnapshot();
      if (next.status === "ended") {
        ended = true;
        generation += 1;
        setState({ status: "anonymous" });
      } else if (ended && next.status === "confirmed") {
        // Confirmation carries no identity. Resolve afresh rather than revealing
        // the previous account, and invalidate any pre-loss request completion.
        ended = false;
        setState({ status: "unknown" });
        resolveIdentity();
      }
      // Intentional logout resets the observation to unknown. Preserve its
      // existing disabled "Signing out…" control until the full navigation.
    });
    if (!ended) resolveIdentity();
    return () => { current = false; generation += 1; unsubscribe(); };
  }, []);

  return observation.status === "ended" ? { status: "anonymous" } : state;
}
