# ADR-010 — M4 entitlement decisions

**Status:** Accepted
**Date:** 2026-08-18
**Amends:** `docs/architecture.md` §10 M4 (§1 below) and §4.5 rule 3 (§4 below).
**Context:** M4 — Entitlements. CLAUDE.md §5 gates the entitlement model on
explicit approval and §9 names it the most expensive place in this codebase to
guess, so each of these was asked rather than assumed.

Spec: `docs/specs/m4-entitlements.md`.

---

## 1. No `Plan` model in M4 — amends architecture.md §10

`architecture.md` §10 M4 lists `Subscription`, `Plan`, `AccessOverride`.
CLAUDE.md §3 says a **single subscription tier**, monthly or yearly.

With one tier the resolver never asks *which* plan; access follows from
subscription **status**. Everything a `Plan` row would carry — price, interval,
currency, provider price id — is billing, and the standing rule while the
payment provider is undecided (CLAUDE.md §11 #1) is: do not model billing.

**Decision.** `Plan` is deferred to M8, where it arrives with the provider that
gives it meaning.

**Reopens if** a second tier is planned. That changes `resolve_access` from
"is the subscription live" to "does this subscription cover this content" — a
different function, not a new branch.

---

## 2. A trial grants preview lessons only

**Decision.** `TRIALING` grants exactly the lessons already flagged
`is_preview`. No eligibility flag on `Course`, no relation from `Subscription`
to courses, no lesson quota — therefore no new schema and no dependency on the
progress tracking that does not exist until M7.

Considered and set aside: a per-course `is_trial_eligible` flag set by admins
during review; courses named on the subscription at trial start; a "first N
lessons" quota, which needs consumption tracking from M7.

**The consequence, recorded so it is not later mistaken for a bug.** Branch 1
of the resolver allows preview lessons to *everyone*, anonymous included. So a
trial grants no content an unauthenticated browser cannot already reach. For
gated content `TRIALING` is a **denial branch carrying a better reason** —
`TRIAL_SCOPE` with `cta=upgrade` instead of the anonymous `cta=subscribe`.

This is coherent: the subscription lifecycle stays real and exercised end to
end before M8 touches it, and M9 inherits a state to build on. It is **not** a
trial that converts by showing paid content. If conversion becomes the goal,
M9 revisits this — most likely with the per-course flag set aside above.

---

## 3. `PAST_DUE` keeps access for 7 days

**Decision.** Seven days, as a named setting `ENTITLEMENT_GRACE_PERIOD`, not a
literal.

A business decision with revenue consequences both ways: too short and a
failed card locks out a paying customer mid-lesson; too long and access
continues after payment stops. Seven days covers a typical card retry cycle.

**As a setting**, because the boundary is a tested value — the resolver has a
test at exactly the edge and one second past it — and because changing it
should be configuration, not a code change.

---

## 4. The resolver is not cached in M4 — amends architecture.md §4.5 rule 3

§4.5 rule 3 specifies "cached in Redis with a short TTL, invalidated on every
webhook".

**There are no webhooks until M8.** A cache added now has no invalidation
source and can only expire by TTL, which means a cancelled or expired
subscription keeps access until the TTL lapses. That is a caching bug that
gives away the product, introduced before anything needs the cache — and
§4.5's own rule 3 assumes the invalidation that does not yet exist.

**Decision.** Build `resolve_access` uncached. Pin its query cost with an
ADR-009 test. Add caching in M8, in the same change as the webhook that
invalidates it.

The signature does not change, so nothing is harder later. The ADR-009 test
also gives M8 a number to justify the cache against, rather than adding one on
principle.

---

## 5. What none of these change

- **Invariant 3 holds exactly.** One resolver, returning a reason, never a
  bare boolean, never a stored `has_access` column maintained by a job.
- **Billing is still unmodelled.** No prices, invoices, payment methods, tax or
  currency anywhere in M4.
- **M4 still comes before M8** for the reason CLAUDE.md §10 gives: entitlement
  is built and tested against a fake provider so that billing becomes a thin
  event source feeding a system that already works.
