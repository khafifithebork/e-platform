/** Presentation observations only; Django remains the session/access authority. */
export type SessionStatus =
  | Readonly<{ status: "unknown" }>
  | Readonly<{ status: "confirmed" }>
  | Readonly<{ status: "ended"; detail: string }>;

type Ticket = Readonly<{ epoch: number; sequence: number; confirmed: boolean; observable: boolean }> | null;
const UNKNOWN: SessionStatus = { status: "unknown" };
const CONFIRMED: SessionStatus = { status: "confirmed" };

export function createSessionStatusStore() {
  let snapshot: SessionStatus = UNKNOWN;
  let epoch = 0;
  let sequence = 0;
  let lastObservation = 0;
  let operation: number | null = null;
  const listeners = new Set<() => void>();

  function publish(next: SessionStatus) {
    if (snapshot === next) return;
    snapshot = next;
    for (const notify of listeners) notify();
  }

  function current(ticket: Ticket): ticket is NonNullable<Ticket> {
    return typeof window !== "undefined" && ticket !== null &&
      ticket.observable && ticket.epoch === epoch && ticket.sequence >= lastObservation && operation === null;
  }

  return {
    begin(intent?: "login" | "logout"): Ticket {
      if (typeof window === "undefined") return null;
      sequence += 1;
      if (intent) {
        // Invalidate requests from before an intentional auth operation. Until
        // it settles, a concurrent /me response cannot establish a new session.
        epoch += 1;
        operation = sequence;
        lastObservation = sequence;
        publish(UNKNOWN);
      }
      return { epoch, sequence, confirmed: snapshot.status === "confirmed", observable: operation === null };
    },
    finish(ticket: Ticket) {
      if (typeof window !== "undefined" && ticket?.epoch === epoch && operation === ticket.sequence) {
        operation = null;
      }
    },
    confirm(ticket: Ticket) {
      if (!current(ticket)) return;
      lastObservation = ticket.sequence;
      publish(CONFIRMED);
    },
    authenticationRequired(ticket: Ticket, detail: string) {
      if (!current(ticket) || !ticket.confirmed || snapshot.status !== "confirmed") return;
      // Old successes must not undo this transition when their bodies arrive
      // later. A fresh /me request can confirm a subsequently restored session.
      epoch += 1;
      lastObservation = ticket.sequence;
      publish({ status: "ended", detail });
    },
    getSnapshot: (): SessionStatus => typeof window === "undefined" ? UNKNOWN : snapshot,
    getServerSnapshot: (): SessionStatus => UNKNOWN,
    subscribe(notify: () => void) {
      if (typeof window === "undefined") return () => {};
      listeners.add(notify);
      return () => { listeners.delete(notify); };
    },
  };
}

// Every mutation is browser-guarded: the server never retains per-user state.
export const sessionStatus = createSessionStatusStore();
