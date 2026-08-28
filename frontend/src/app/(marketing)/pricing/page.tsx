import type { Metadata } from "next";
import Link from "next/link";

import { PricingPlans } from "@/components/pricing/PricingPlans";
import { PRICE_BOOK } from "@/lib/pricing";

export const metadata: Metadata = {
  title: "Pricing",
  description: "One subscription covering every course, billed monthly or yearly.",
};

/**
 * Pricing — the page, deliberately not the price.
 *
 * **§11 #1 is unresolved**: the payment provider and the operating jurisdiction
 * are undecided. Stripe is unavailable to Moroccan merchants and a merchant of
 * record may be required, which changes who the contracting party is, whether
 * a figure is VAT-inclusive, and what the refund terms have to say. §6 forbids
 * inventing any of that.
 *
 * So this renders the unannounced state, and the priced state is written and
 * tested beside it. `PRICE_BOOK` in `src/lib/pricing.ts` is the single place a
 * figure lands.
 *
 * **What the page can say honestly** is the shape, because the shape is a
 * product fact rather than a commercial one (CLAUDE.md §3): one tier, monthly
 * or yearly, covering the whole catalogue. And it can say what is free right
 * now — preview lessons are readable by an anonymous visitor, which
 * `resolver.py` allows before it looks at a user at all.
 *
 * **No trial is mentioned.** One exists in the data model and can be started
 * by `manage.py billing start --trial-days`; there is no self-serve path to
 * it. Offering one here would fail at the moment somebody decided to pay.
 */
export default function PricingPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-12 px-6 py-16">
      <header className="flex flex-col gap-4">
        <h1 className="font-display text-4xl tracking-tight text-ink">Pricing</h1>
        <p className="max-w-prose text-lg leading-relaxed text-ink-muted">
          One subscription, every course. No per-course purchases, no tiers that
          hold half the catalogue back.
        </p>
      </header>

      <PricingPlans prices={PRICE_BOOK} />

      <section aria-labelledby="included" className="flex flex-col gap-6">
        <h2 id="included" className="font-display text-2xl text-ink">
          What a subscription covers
        </h2>

        <ul className="flex flex-col gap-3 text-ink-muted">
          <li>Every published course, at every level, in every language.</li>
          <li>Transcripts and subtitles on every spoken lesson.</li>
          <li>Progress that resumes on whichever device you pick up next.</li>
          <li>New courses as they are approved, at no extra cost.</li>
        </ul>
      </section>

      <section aria-labelledby="free" className="flex flex-col gap-4">
        <h2 id="free" className="font-display text-2xl text-ink">
          What you can do without paying
        </h2>
        <p className="max-w-prose text-ink-muted">
          The catalogue is public: every course, its outline and its lesson list
          are readable by anyone. Lessons marked{" "}
          <span className="font-medium text-ink">Free preview</span> are
          watchable without an account at all.
        </p>
        <Link href="/courses" className="text-accent hover:text-accent-hover">
          Browse the catalogue
        </Link>
      </section>
    </div>
  );
}
