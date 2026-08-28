import Link from "next/link";

import { formatPrice, yearlySavingPercent, type PriceBook } from "@/lib/pricing";

/**
 * The plans, in whichever of two states the product is in.
 *
 * **Both states are built and both are tested**, which is the point of writing
 * this now rather than waiting for §11 #1. The unannounced state is what ships
 * today; the priced state is exercised in tests with a fabricated price book
 * that never reaches the bundle. When the decision is made, the work is
 * setting `PRICE_BOOK` — not building a page under time pressure on the day
 * pricing is agreed.
 *
 * One subscription covering everything is a product fact (CLAUDE.md §3), not a
 * price, so the page can describe the shape honestly while the figure is
 * unknown.
 */
export function PricingPlans({ prices }: { prices: PriceBook | null }) {
  if (prices === null) return <Unannounced />;

  const saving = yearlySavingPercent(prices);

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <Plan
        name="Monthly"
        price={formatPrice(prices.monthly)}
        period="per month"
        note="Cancel any time. Access continues to the end of the period you paid for."
      />
      <Plan
        name="Yearly"
        price={formatPrice(prices.yearly)}
        period="per year"
        // `saving` is null when a year costs as much as twelve months, and
        // then nothing is claimed. "Save 0%" is worse than saying nothing.
        note={saving === null ? "Billed once a year." : `Billed once a year — save ${saving}%.`}
      />
    </div>
  );
}

function Plan({
  name,
  price,
  period,
  note,
}: {
  name: string;
  price: string;
  period: string;
  note: string;
}) {
  return (
    <section
      aria-labelledby={`plan-${name.toLowerCase()}`}
      className="flex flex-col gap-3 rounded-[--radius-lg] border border-line bg-surface p-6"
    >
      <h2 id={`plan-${name.toLowerCase()}`} className="font-medium text-ink">
        {name}
      </h2>
      <p className="flex items-baseline gap-2">
        <span className="font-display text-3xl text-ink">{price}</span>
        {/*
         * The period is part of the price, not a caption. Read on its own,
         * "€9.90" followed later by "per month" can be separated by a screen
         * reader's navigation — so they sit in one paragraph.
         */}
        <span className="text-sm text-ink-muted">{period}</span>
      </p>
      <p className="text-sm text-ink-muted">{note}</p>
    </section>
  );
}

/**
 * What the page says while there is no price.
 *
 * **Not a placeholder, and not a fake number greyed out.** A visitor is told
 * plainly that pricing is not announced, which is true, and pointed at the
 * catalogue, which they can use right now. Inventing a figure to fill the
 * space would be a commitment nobody made; showing "€—" would be a broken page
 * pretending to be a design.
 */
function Unannounced() {
  return (
    <div className="flex flex-col gap-4 rounded-[--radius-lg] border border-line bg-surface p-6">
      <h2 className="font-medium text-ink">Pricing is not announced yet</h2>
      <p className="max-w-prose text-ink-muted">
        There will be one subscription covering every course, billed monthly or
        yearly. The amount is not set, and we would rather leave this blank than
        publish a figure that changes.
      </p>
      <p className="max-w-prose text-ink-muted">
        The catalogue is readable now, and preview lessons are free to watch
        without an account.
      </p>
      <Link href="/courses" className="text-accent hover:text-accent-hover">
        Browse the catalogue
      </Link>
    </div>
  );
}
