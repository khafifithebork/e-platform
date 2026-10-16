"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { LoadFailure } from "@/components/ui/LoadFailure";
import { ApiError, api, type Me } from "@/lib/api/client";

/**
 * What the product knows about you, and nothing it does not.
 *
 * **Every field here comes from `/auth/me/`.** Nothing is derived, computed or
 * inferred — most importantly not the access state, which is the server's own
 * decision and its own words. Invariant 3: there is one entitlement resolver and
 * the frontend never re-derives its rules.
 *
 * **What this page deliberately does not offer** is worth stating, because the
 * absences look like oversights:
 *
 * - **No display-name editing.** `StudentProfileSerializer` is documented "Output
 *   only" and there is no endpoint to write it.
 * - **No email change.** No endpoint.
 * - **No account deletion.** ADR-036 §5 leaves retention questions unresolved.
 *   Data export is provided separately by `DataExport` on the same page.
 */

type State =
  | { status: "loading" }
  | { status: "ready"; me: Me }
  | { status: "anonymous" }
  | { status: "failed" };

export function AccountDetails() {
  const [state, setState] = useState<State>({ status: "loading" });
  /** Bumped to retry a failed load. See `LoadFailure`. */
  const [attempt, setAttempt] = useState(0);

  /** Re-run the load that failed. The reset is here, not in the effect. */
  function retry() {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  useEffect(() => {
    let current = true;

    api
      .me()
      .then((me) => {
        if (current) setState({ status: "ready", me });
      })
      .catch((error: unknown) => {
        if (!current) return;

        // **Anonymous is an answer, not a failure**, and separating the two is the
        // difference between "sign in" and "something went wrong" — the same
        // distinction `MyCourses` and `AuthMenu` make, for the same reason.
        if (error instanceof ApiError && error.isNotAuthenticated) {
          setState({ status: "anonymous" });
          return;
        }

        setState({ status: "failed" });
      });

    return () => {
      current = false;
    };
  }, [attempt]);

  if (state.status === "loading") {
    return <p className="text-ink-muted">Loading your account…</p>;
  }

  if (state.status === "anonymous") {
    return (
      <div className="flex flex-col items-start gap-4">
        <p className="text-ink-muted">Sign in to see your account.</p>
        <Link href="/login" className="text-accent underline underline-offset-4">
          Sign in
        </Link>
      </div>
    );
  }

  if (state.status === "failed") {
    // "Reloading the page usually fixes it" was advice where a button belonged —
    // and reloading would also discard anything typed into the password form below.
    return (
      <LoadFailure onRetry={retry}>
        Your account could not be loaded.
      </LoadFailure>
    );
  }

  const { me } = state;

  return (
    <div className="flex min-w-0 flex-col gap-10 sm:gap-12">
      <section aria-labelledby="who" className="flex flex-col gap-4">
        <h2 id="who" className="font-display text-2xl text-ink">
          Your details
        </h2>

        <dl className="flex min-w-0 flex-col gap-5 border-t border-line pt-5">
          <Row term="Email">{me.email}</Row>

          <Row term="Email confirmed">
            {me.is_email_verified ? (
              "Yes"
            ) : (
              <span className="flex flex-wrap items-baseline gap-2">
                <span>Not yet</span>
                {/*
                 * The other half of the loop batch one opened. Before
                 * `/verify-email` existed this state could be *reported* and not
                 * acted on: the token had nowhere to go.
                 */}
                <Link href="/verify-email" className="text-accent underline underline-offset-4">
                  Confirm it now
                </Link>
              </span>
            )}
          </Row>

          {/*
           * Shown only when set. The API documents it as empty when unset, and an
           * empty row invites the reading that the field is broken rather than
           * unused. There is no way to set it from here — see the note above.
           */}
          {me.profile?.display_name ? (
            <Row term="Display name">{me.profile.display_name}</Row>
          ) : null}

          {/*
           * Role, for the two accounts that are not students. A learner seeing
           * "Student" learns nothing; an instructor or an admin seeing their role
           * is being told which surfaces apply to them.
           */}
          {me.role !== "STUDENT" ? <Row term="Role">{me.role}</Row> : null}
        </dl>
      </section>

      <AccessSummary access={me.access} />
    </div>
  );
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 sm:flex-row sm:items-baseline sm:gap-6">
      <dt className="text-sm text-ink-muted sm:w-44 sm:shrink-0">{term}</dt>
      <dd className="min-w-0 text-ink [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

/**
 * Where the account stands with the subscription, in the server's words.
 *
 * **`label` is displayed and `reason` is never interpreted here.** The resolver can
 * return twelve reasons at account level and it carries a label for each, added to
 * `AccessSerializer` on 2026-09-29 for exactly this. Restating them client-side
 * would be a second copy of that vocabulary — which is the mistake `denial.ts`
 * documents, having branched for nine milestones on two reasons that never existed.
 *
 * `cta` is the server's suggestion of what to offer next, and the only thing this
 * component adds is where each of the three leads.
 *
 * **No price and no checkout.** CLAUDE.md §11 #1 is unresolved, so "subscribe"
 * lands on `/pricing`, which says plainly that pricing is not announced — the same
 * destination `denial.ts` uses, and for the same reason: sending somebody to a
 * payment page that cannot take payment is worse than telling them the truth.
 */
function AccessSummary({ access }: { access: Me["access"] }) {
  return (
    <section aria-labelledby="access" className="flex flex-col gap-4">
      <h2 id="access" className="font-display text-2xl text-ink">
        Course access
      </h2>

      <div className="flex flex-col gap-3 border-t border-line pt-5 [overflow-wrap:anywhere]">
        <p className="text-ink">
          {access.allowed
            ? "You have access to every published course."
            : "You do not currently have access to the full catalogue."}
        </p>

        {/* The server's label, verbatim. ADR-004: echo the API's wording. */}
        <p className="text-sm text-ink-muted">{access.label}</p>

        <AccessAction cta={access.cta} />
      </div>
    </section>
  );
}

/**
 * The three destinations, keyed by the generated union.
 *
 * `Record<Cta, …>` rather than a switch, so **adding a CTA in M8 is a compile
 * error** rather than a silently missing button. The `null` case is a grant, or
 * `GRACE_PERIOD_ENDED` — where the server sends `update_payment` and there is no
 * billing portal to send anyone to yet.
 */
const DESTINATION: Record<NonNullable<Me["access"]["cta"]>, { label: string; href: string }> = {
  login: { label: "Sign in", href: "/login" },
  subscribe: { label: "See what a subscription covers", href: "/pricing" },
  // Points at pricing too, and that is the honest placeholder rather than a
  // pretend portal: there is no payment provider (§11 #1), so there is nowhere to
  // update a card. M8 replaces this with a real destination.
  update_payment: { label: "See what a subscription covers", href: "/pricing" },
};

function AccessAction({ cta }: { cta: Me["access"]["cta"] }) {
  if (cta === null || cta === undefined) return null;

  const destination = DESTINATION[cta];

  return (
    <p>
      <Link href={destination.href} className="text-accent underline underline-offset-4">
        {destination.label}
      </Link>
    </p>
  );
}
