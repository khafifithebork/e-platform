/**
 * The price book, and the tripwire on it.
 *
 * The arithmetic here is short and the consequence of getting it wrong is a
 * number on a public page that overstates a discount — which is a commercial
 * claim, not a rendering bug.
 */

import { describe, expect, it } from "vitest";

import { PRICE_BOOK, formatPrice, yearlySavingPercent, type PriceBook } from "@/lib/pricing";

/** Never exported, never bundled — only these tests exercise a priced state. */
const FAKE: PriceBook = {
  monthly: { amount: 1000, currency: "EUR" },
  yearly: { amount: 9000, currency: "EUR" },
  trialDays: null,
};

describe("the tripwire", () => {
  it("is still unpriced", () => {
    /**
     * **This test is meant to be deleted, once, deliberately.**
     *
     * CLAUDE.md §11 #1 is unresolved and §6 forbids inventing a price. When
     * the decision is made, whoever sets `PRICE_BOOK` deletes this in the same
     * commit — which is a visible act in a diff somebody reviews as a business
     * decision.
     *
     * The failure it exists to prevent is a price arriving inside a copy edit.
     * A structural check over the route group already stops a figure being
     * typed into markup; this stops it arriving through the front door with
     * nobody noticing that a commercial commitment was made.
     */
    expect(PRICE_BOOK).toBeNull();
  });
});

describe("formatting", () => {
  it("renders minor units as a decimal amount", () => {
    // 990 is €9.90, not €990. Storing minor units is what keeps money out of
    // floating point; dividing in the wrong place is how it gets back in.
    expect(formatPrice({ amount: 990, currency: "EUR" })).toMatch(/9[.,]90/);
  });

  it("includes the currency", () => {
    expect(formatPrice({ amount: 990, currency: "EUR" })).toMatch(/€|EUR/);
  });

  it("does not lose the cents on a round amount", () => {
    // `Intl` keeps two fraction digits for EUR, so 1000 is "10.00" — a
    // hand-rolled formatter that trimmed trailing zeros would render "€10"
    // beside "€9.90" and look like two different designs.
    expect(formatPrice({ amount: 1000, currency: "EUR" })).toMatch(/10[.,]00/);
  });

  it("handles a zero-decimal currency without inventing cents", () => {
    // The yen has no minor unit. Dividing by 100 unconditionally is the bug
    // this notices, and `Intl` is what makes it survivable rather than a
    // formatter that assumes two decimals everywhere.
    expect(formatPrice({ amount: 1000, currency: "JPY" })).not.toMatch(/1000[.,]00/);
  });
});

describe("the yearly saving", () => {
  it("is the difference against twelve monthly payments", () => {
    // 12 × 1000 = 12000; a yearly price of 9000 saves 3000, which is 25%.
    expect(yearlySavingPercent(FAKE)).toBe(25);
  });

  it("rounds down, never up", () => {
    // The page must not claim a larger discount than the arithmetic supports.
    // 12 × 1000 = 12000 against 11999 is 0.008%, which is 0 and not 1.
    expect(
      yearlySavingPercent({ ...FAKE, yearly: { amount: 11999, currency: "EUR" } }),
    ).toBe(0);
  });

  it("says nothing when a year costs the same as twelve months", () => {
    // "Save 0%" is worse than saying nothing, and it is what a naive
    // percentage renders on a yearly plan priced at parity.
    expect(
      yearlySavingPercent({ ...FAKE, yearly: { amount: 12000, currency: "EUR" } }),
    ).toBeNull();
  });

  it("says nothing when a year costs more", () => {
    // A negative saving displayed as "save -8%" is the kind of thing that
    // reaches production because nobody prices a year above twelve months on
    // purpose — until a currency conversion does it for them.
    expect(
      yearlySavingPercent({ ...FAKE, yearly: { amount: 13000, currency: "EUR" } }),
    ).toBeNull();
  });

  it("does not divide by zero on a free monthly plan", () => {
    expect(
      yearlySavingPercent({ ...FAKE, monthly: { amount: 0, currency: "EUR" } }),
    ).toBeNull();
  });
});
