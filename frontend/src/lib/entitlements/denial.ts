import type { components } from "@/types/api";

/**
 * What each refusal means, in one place.
 *
 * **This replaces a table that had drifted from the server for nine
 * milestones.** `LessonPlayer` has carried its own denial messages since M7,
 * keyed on `SUBSCRIPTION_PAST_DUE` and `NOT_AUTHENTICATED` — **neither of
 * which has ever been a `Reason`**. Two branches that could not fire, and four
 * real refusals with no branch at all, including `LOGIN_REQUIRED`, which is
 * what every signed-out visitor gets.
 *
 * Nothing caught it because the codes were plain strings on both sides. They
 * are now a schema enum (`ReasonEnum`), so this table is keyed by a generated
 * union and **TypeScript refuses to compile if a reason is added and not
 * handled** — which is the guard that matters, because M8 and M9 will add
 * reasons.
 *
 * `resolve_access` returns a reason and never a bare boolean (invariant 3).
 * Six distinct refusals exist precisely so the interface can say six different
 * things; collapsing them into one paywall throws away the work M4 did.
 */

export type Reason = components["schemas"]["ReasonEnum"];
export type Cta = components["schemas"]["CtaEnum"];

/** The six that mean "no". The other eight are grants. */
export type DenialReason = Extract<
  Reason,
  | "LOGIN_REQUIRED"
  | "NO_SUBSCRIPTION"
  | "SUBSCRIPTION_EXPIRED"
  | "TRIAL_EXPIRED"
  | "TRIAL_SCOPE"
  | "GRACE_PERIOD_ENDED"
>;

export interface Refusal {
  /** A heading. States what is true, not what went wrong. */
  title: string;
  /** One sentence of explanation. No blame, no jargon. */
  detail: string;
  /** Where the person goes next, or `null` when there is nowhere useful. */
  action: { label: string; href: string } | null;
}

/**
 * Where a refusal points.
 *
 * **Not a checkout.** There is no self-serve subscription and no price
 * (CLAUDE.md §11 #1), so every "subscribe" CTA lands on `/pricing`, which says
 * plainly that pricing is not announced. Sending somebody to a payment page
 * that cannot take payment is worse than telling them the truth.
 */
const SUBSCRIBE = { label: "See what a subscription covers", href: "/pricing" };

/**
 * Keyed by the generated union, so this is exhaustive by construction.
 *
 * The wording avoids two habits. It does not apologise — a lapsed subscription
 * is not an error and saying "sorry" implies something went wrong. And it does
 * not say "upgrade", which implies a tier structure this product does not have:
 * there is one subscription covering everything.
 */
export const REFUSALS: Record<DenialReason, Refusal> = {
  LOGIN_REQUIRED: {
    title: "Sign in to watch this lesson",
    detail: "This lesson is part of a course that needs an account.",
    action: { label: "Sign in", href: "/login" },
  },
  NO_SUBSCRIPTION: {
    title: "This lesson needs a subscription",
    detail: "One subscription covers every course. Preview lessons are free to watch.",
    action: SUBSCRIBE,
  },
  SUBSCRIPTION_EXPIRED: {
    title: "Your subscription has ended",
    detail: "Your progress is kept. Subscribing again picks up where you left off.",
    action: SUBSCRIBE,
  },
  TRIAL_EXPIRED: {
    title: "Your trial has ended",
    detail: "Your progress is kept. Subscribing picks up where you left off.",
    action: SUBSCRIBE,
  },
  TRIAL_SCOPE: {
    // The resolver's own label is "Not included in your trial". The trial is
    // scoped rather than a full subscription, and *what* scopes it is still
    // undecided (STATUS.md, blocking M9) — so this says what is true without
    // claiming a rule nobody has settled.
    title: "This lesson is not part of your trial",
    detail: "A subscription covers every course, including this one.",
    action: SUBSCRIBE,
  },
  GRACE_PERIOD_ENDED: {
    // The one refusal that is not "subscribe". The person is a paying customer
    // whose payment failed, and sending them to a pricing page tells them to
    // buy something they already bought.
    title: "There is a problem with your payment",
    detail:
      "We could not take the last payment, and the grace period has ended. " +
      "Updating your payment details restores access straight away.",
    action: null,
  },
};

/** The CTA the server suggested, if the interface wants to branch on it. */
export const CTA_FOR: Record<DenialReason, Cta> = {
  LOGIN_REQUIRED: "login",
  NO_SUBSCRIPTION: "subscribe",
  SUBSCRIPTION_EXPIRED: "subscribe",
  TRIAL_EXPIRED: "subscribe",
  TRIAL_SCOPE: "subscribe",
  GRACE_PERIOD_ENDED: "update_payment",
};

function isDenialReason(reason: string): reason is DenialReason {
  return reason in REFUSALS;
}

/**
 * The refusal to show for whatever the server said.
 *
 * **Falls back rather than throwing**, and the fallback is deliberately
 * uninformative. A reason this build does not recognise means the server is
 * ahead of the client — a deploy in progress, or a reason added in M8 — and
 * inventing an explanation for it would be guessing at somebody's billing
 * state. The generated union makes a *known* omission a compile error; this
 * covers the case where the running server is simply newer.
 */
export function refusalFor(reason: string | null | undefined): Refusal {
  if (reason && isDenialReason(reason)) return REFUSALS[reason];

  return {
    title: "You do not have access to this lesson",
    detail: "Your account does not currently include this course.",
    action: SUBSCRIBE,
  };
}
