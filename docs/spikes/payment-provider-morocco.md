# Spike — Payment provider for a Moroccan seller

**Date:** 2026-08-30
**Status:** research. **Decides nothing** — CLAUDE.md §11 #1 stays open.
**For:** M8 (blocked entirely), and the price on `/pricing` (M15 T8 shipped it
with `PRICE_BOOK = null`)

---

## Why this is a spike and not an ADR

§11 #1 asks two questions — payment provider *and* operating jurisdiction — and
the second is a legal and tax question about a Moroccan business, not an
engineering one. An ADR here would record a decision nobody has made.

**Nothing below is tax or legal advice.** Two findings need a Moroccan
accountant before they can be acted on, and they are marked.

---

## 1. The constraint is the entity, not the API

CLAUDE.md §11 #1 says *"Stripe is unavailable to Moroccan merchants; a merchant
of record may be required."* That is the right instinct and it is the smaller
half of the problem. Operating as **auto-entrepreneur**:

| Constraint | Consequence |
|---|---|
| **MAD 200,000/yr cap** on services (~$20k) | A subscription business outgrows the status |
| **Cannot hold a convertible dirham account** for foreign income — companies can | Directly affects taking EUR/USD revenue |
| Quarterly **Service Export Report** to Office des Changes | Ongoing obligation |
| **30% withholding above MAD 80,000 from a single client** | ⚠️ **A merchant of record makes 100% of revenue arrive from one payer** |

**The last row is the one to take to an accountant.** An MoR is structurally one
client paying you everything, which is the shape that rule appears to target. If
it applies, it changes the arithmetic in §3 completely and probably points at an
SARL rather than auto-entrepreneur — which is the *jurisdiction* half of §11 #1
that has been open since M4.

⚠️ **Needs a Moroccan accountant.** Sourced from public guides, not from an
authority, and this is exactly the class of fact CLAUDE.md §6 forbids inventing.

---

## 2. The providers, like-for-like

Headline rates mislead here, because this business is **subscriptions** sold
**internationally**. Surcharges that look conditional are unconditional for us.

| Provider | Headline | **Real rate for this business** | Source |
|---|---|---|---|
| **Creem** | 3.9% + $0.40 | **3.9% + $0.40** — claims no international card fee | pricing page |
| **Paddle** | 5% + 50¢ | **5% + 50¢** — verified all-in | pricing page |
| **Dodo** | "4% + 40¢" | **6% + 40¢** — +1.5% international, +0.5% subscriptions | pricing page |
| **Polar** | 5% + 50¢ | +1.5% international reported — **unverified**, pricing page 404s | secondary |
| **Lemon Squeezy** | 5% + 50¢ | Now Stripe-owned — inherits the country problem we started with | secondary |

**Dodo's headline does not apply to us.** Every transaction is both
international and a subscription, so both surcharges always apply and it lands
above Paddle, not below. It also charges $30/dispute and $1/refund, which Paddle
does not.

**Most third-party comparison tables circulating for these providers are written
by one of the vendors.** The figures above come from each provider's own pricing
page for that reason.

### 2.1 The fixed fee is half the cost at a $10 price point

| Monthly price | 5% | +50¢ as % | Effective |
|---:|---:|---:|---:|
| $10 | 5.0% | 5.0% | **10.0%** |
| $15 | 5.0% | 3.3% | 8.3% |
| $20 | 5.0% | 2.5% | 7.5% |
| $30 | 5.0% | 1.7% | 6.7% |

**Annual billing is the largest single lever available.** One transaction a year
instead of twelve:

| Billing | Price | Effective |
|---|---|---:|
| Monthly | $10/mo | **10.0%** |
| Annual | $100/yr | **5.5%** |

At 1,000 subscribers that is ~$450/month — ten times the entire infrastructure
bill. The product already sells both (CLAUDE.md §3).

---

## 3. Cheaper exists, and it costs something this codebase cares about

**Creem is genuinely cheaper than Paddle** — 7.9% against 10.0% at $10/month,
about $210/month saved at 1,000 subscribers.

**But Creem signs webhooks as HMAC-SHA256 over the raw body only** — header
`creem-signature`, **no timestamp, no replay window**. That is precisely the gap
ADR-013 §6 recorded against M5's fake provider:

> The webhook signature has no timestamp. Our scheme accepts a valid old
> signature indefinitely… Real providers bound this with a timestamp, and
> **M8's adapter must add it.**

**This cannot be fixed from our side.** If the sender does not sign a timestamp,
no adapter can verify one. Creem does send an event `id`, so invariant 8's
`WebhookEvent` unique constraint still catches duplicates — what is not caught
is a captured payload replayed months later against an endpoint that grants paid
access.

**Paddle signs `{ts}:{raw_body}`** with a `ts=…;h1=…` header and a ~5-second
tolerance, which closes ADR-013 §6 for free rather than as work.

---

## 4. Skipping the MoR entirely, and where it breaks even

ADR-002 §2.2 names this as *"the single biggest lever in the business"*.

| | Cost |
|---|---|
| Stripe Atlas (US LLC) | **$500 once**, then ~$400/yr ≈ $33/mo |
| Tax compliance (Quaderno) | from **$49/mo** |
| Stripe fees | ~2.9% + 30¢ |

That is **~$82/month fixed before a single sale**. Break-even against Paddle:

| Billing | Break-even |
|---|---|
| $10/month | **~200 subscribers** |
| $100/year | **~430 subscribers** |

**Below that, Paddle is cheaper than Stripe.** ADR-002 §2.2 says incorporating
"saves ~$200/mo" at 1,000 subscribers, which is true and omits the fixed costs —
so it reads as free money at any scale. It is not.

⚠️ **Needs a Moroccan accountant.** A Moroccan resident owning a US LLC has
Moroccan tax and Office des Changes implications not assessed here.

---

## 5. What could not be verified

| Unknown | Why it matters |
|---|---|
| **Neither Paddle nor Creem publishes seller-country eligibility** | The whole Morocco question. Paddle's help page says it works with businesses "anywhere in the world" except 28 listed countries — **Morocco is not among them** — but that page does not separate sellers from buyers |
| **Paddle payout methods and currencies to a Moroccan bank** | Undocumented publicly. Could add 1–2% |
| **Paddle chargeback fee** | Polar publishes $15; Paddle's is not stated |
| **Paddle prices products under $10** | Their page says "contact us for custom pricing" below $10, so the published rate may not apply at $9.99 |
| **Creem seller countries and payout rails** | Not published |

The first four are one email to Paddle support:

> Can a Morocco-registered company hold a Paddle seller account, and what payout
> methods and currencies are available to a Moroccan bank account?

---

## 6. Where this points, without deciding

**Paddle**, on two grounds that are not about price: it closes ADR-013 §6's
known gap, and its subscription lifecycle is mature in a way a two-year-old
competitor's is not — which matters more than 2% for a system that gates paid
content on webhook delivery.

**The price difference is $0 today**, because there are no subscribers. The
sensible shape is to choose on webhook integrity now and set a **revisit trigger
at ~200 paying subscribers**, where the Stripe route begins to pay for itself.

**Nothing here is actionable until the accountant answers §1.** If the
single-client withholding rule applies to MoR revenue, it dominates every number
above.

---

## Sources

- [Paddle — pricing](https://www.paddle.com/pricing)
- [Paddle — supported countries](https://www.paddle.com/help/start/intro-to-paddle/which-countries-are-supported-by-paddle)
- [Paddle — webhook signature verification](https://developer.paddle.com/webhooks/about/signature-verification/)
- [Creem — pricing](https://www.creem.io/pricing)
- [Creem — webhooks](https://docs.creem.io/code/webhooks)
- [Dodo Payments — pricing](https://dodopayments.com/pricing)
- [Freelancing legally in Morocco](https://grey.co/blog/freelancing-legally-in-morocco-licences-taxes-and-foreign-income-rules)
- [Office des Changes](https://www.oc.gov.ma/en)
