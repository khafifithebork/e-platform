/**
 * Both states of the pricing page.
 *
 * The priced state ships today rendering nothing, because `PRICE_BOOK` is
 * null — so these tests are the only thing exercising it until §11 #1 is
 * answered. That is the reason to write them now rather than later: the
 * alternative is building a pricing page under time pressure on the day
 * pricing is agreed, which is exactly when a mistake in it is most expensive.
 *
 * The fabricated price book here never reaches the bundle. It exists so the
 * page can be proved before there is a real figure to prove it with.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PricingPlans } from "@/components/pricing/PricingPlans";
import type { PriceBook } from "@/lib/pricing";

const FAKE: PriceBook = {
  monthly: { amount: 1000, currency: "EUR" },
  yearly: { amount: 9000, currency: "EUR" },
  trialDays: null,
};

describe("while there is no price", () => {
  it("says so plainly", () => {
    render(<PricingPlans prices={null} />);

    expect(screen.getByText(/not announced yet/i)).toBeInTheDocument();
  });

  it("shows no figure at all", () => {
    // Not a placeholder, not "€—" greyed out. A broken page pretending to be a
    // design is worse than a short one that tells the truth.
    const { container } = render(<PricingPlans prices={null} />);

    expect(container.textContent).not.toMatch(/[$£€]\s?\d/);
  });

  it("still describes the shape, which is a product fact", () => {
    // One tier covering everything, billed monthly or yearly, is CLAUDE.md §3
    // — a product decision, not a commercial one. It can be said honestly
    // while the amount is unknown.
    render(<PricingPlans prices={null} />);

    expect(screen.getByText(/one subscription covering every course/i)).toBeInTheDocument();
  });

  it("points somewhere useful rather than dead-ending", () => {
    // A visitor who came here to spend money and cannot should leave with
    // something to do.
    render(<PricingPlans prices={null} />);

    expect(screen.getByRole("link", { name: /browse the catalogue/i })).toHaveAttribute(
      "href",
      "/courses",
    );
  });

  it("promises no trial", () => {
    // One exists in the data model and cannot be started by a visitor. The
    // page must not offer it until M8 gives them a way.
    render(<PricingPlans prices={null} />);

    expect(screen.queryByText(/trial/i)).not.toBeInTheDocument();
  });
});

describe("once there is a price", () => {
  it("shows both plans", () => {
    render(<PricingPlans prices={FAKE} />);

    expect(screen.getByRole("heading", { name: "Monthly" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Yearly" })).toBeInTheDocument();
  });

  it("renders the amounts, not the minor units", () => {
    // 1000 minor units is €10.00. Rendering "€1000.00" is the bug, and it is
    // the one a reviewer would not notice on a page they skim.
    render(<PricingPlans prices={FAKE} />);

    expect(screen.getByText(/10[.,]00/)).toBeInTheDocument();
    expect(screen.queryByText(/1000[.,]00/)).not.toBeInTheDocument();
  });

  it("states the saving on the yearly plan", () => {
    render(<PricingPlans prices={FAKE} />);

    expect(screen.getByText(/save 25%/i)).toBeInTheDocument();
  });

  it("claims no saving when there is none", () => {
    // The negative. A yearly plan at parity with twelve months must not say
    // "save 0%", and the component must not compute its own answer separately
    // from `yearlySavingPercent`.
    render(
      <PricingPlans prices={{ ...FAKE, yearly: { amount: 12000, currency: "EUR" } }} />,
    );

    expect(screen.queryByText(/save/i)).not.toBeInTheDocument();
    expect(screen.getByText(/billed once a year/i)).toBeInTheDocument();
  });

  it("keeps the period with the amount, not as a loose caption", () => {
    // Read on its own, "€10.00" separated from "per month" is a price with no
    // period — and a screen reader navigating by paragraph can separate them.
    render(<PricingPlans prices={FAKE} />);

    const amount = screen.getByText(/10[.,]00/);

    expect(amount.parentElement?.textContent).toMatch(/per month/i);
  });

  it("names each plan in the accessibility tree", () => {
    render(<PricingPlans prices={FAKE} />);

    expect(screen.getByRole("region", { name: "Monthly" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Yearly" })).toBeInTheDocument();
  });

  it("says what cancelling does", () => {
    // ADR-010 and the resolver: a cancelled subscription keeps access to the
    // end of the paid period. Saying so on the pricing page is the difference
    // between an expected behaviour and a support ticket.
    render(<PricingPlans prices={FAKE} />);

    expect(screen.getByText(/end of the period you paid for/i)).toBeInTheDocument();
  });
});
