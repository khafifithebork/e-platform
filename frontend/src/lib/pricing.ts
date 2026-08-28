/**
 * The one place a price goes.
 *
 * **There is no price yet, and that is a decision nobody has made rather than
 * a value nobody has typed.** CLAUDE.md §11 #1: the payment provider and the
 * operating jurisdiction are unresolved. Stripe is unavailable to Moroccan
 * merchants, a merchant of record may be required, and which one changes what
 * a pricing page may legally say — a VAT-inclusive figure, who the contracting
 * party is, and what the refund terms are.
 *
 * So `PRICE_BOOK` is `null`, the pricing page renders an unannounced state,
 * and **filling this in is one edit in one file** rather than a search through
 * markup for a number somebody hardcoded.
 *
 * `pricing.test.ts` asserts it is still null. That test is a tripwire, not a
 * lock: when the decision is made, deleting it is a deliberate visible act in
 * the same commit that sets the price. The failure mode it exists to prevent
 * is a price appearing in a copy edit that nobody reviews as a business
 * decision.
 *
 * **Amounts are minor units.** 990, not 9.90. Floating-point money is the
 * oldest bug in commerce, and the backend will hold the authoritative figure
 * anyway — this is display only, and it must agree with what the provider
 * charges rather than be rounded into disagreement.
 */

export interface Price {
  /** Minor units — cents, centimes. Never a float. */
  amount: number;
  /** ISO 4217, e.g. "EUR". Decides formatting and the symbol. */
  currency: string;
}

export interface PriceBook {
  monthly: Price;
  /**
   * Charged once a year. The saving against twelve monthly payments is
   * computed, never written down separately — two numbers that must agree are
   * two numbers that will not.
   */
  yearly: Price;
  /**
   * Days of trial, or `null` for none.
   *
   * **Currently meaningless even when set**, and that is deliberate: a trial
   * can only be started by `manage.py billing start --trial-days`, so there is
   * no self-serve path to one. Setting this without M8 would put a promise on
   * the page that the product cannot keep at the moment somebody decides to
   * pay.
   */
  trialDays: number | null;
}

/** `null` until §11 #1 is answered. See this module's docstring. */
export const PRICE_BOOK: PriceBook | null = null;

/**
 * Format a price for display.
 *
 * `Intl.NumberFormat` rather than a symbol table: it puts the symbol where the
 * locale puts it, which is before the number in English and after it in
 * French, and it is already in every runtime this app targets.
 *
 * Undefined locale on purpose — the visitor's own. A price hardcoded to
 * `en-US` formatting shows "€9.90" to someone whose system would write
 * "9,90 €", which reads as a foreign site.
 */
export function formatPrice(price: Price): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: price.currency,
  }).format(price.amount / 100);
}

/**
 * What a year costs versus twelve months of it, as a percentage.
 *
 * Returns `null` when there is nothing to boast about — a yearly plan priced at
 * or above twelve monthly payments should not display a saving of zero or a
 * negative one, and "save 0%" is worse than saying nothing.
 *
 * Rounded down, so the page never claims a larger discount than the arithmetic
 * supports.
 */
export function yearlySavingPercent(prices: PriceBook): number | null {
  const twelveMonths = prices.monthly.amount * 12;
  if (prices.yearly.amount >= twelveMonths || twelveMonths === 0) return null;

  return Math.floor(((twelveMonths - prices.yearly.amount) / twelveMonths) * 100);
}
