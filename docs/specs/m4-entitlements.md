# M4 — Entitlements

**Status:** Delivered, 2026-08-19. Branch `feat/m4-entitlements`.
Outcomes recorded in `docs/adr/010-m4-entitlement-decisions.md`.
**§3.2 remains open and blocks a self-serve trial in M9.**
CLAUDE.md §5 gates the entitlement model on explicit approval, and §9 names
this the most expensive place in the codebase to guess.

Sources: `docs/architecture.md` §4.5 (the resolver), §5.2 (model rationale),
§5.3 (indexes), §7 (threat model), §10 M4. Standing rules: ADR-006 (provoke
the control), ADR-009 (measure, do not reason).

---

## 1. Objective

One function decides whether a person may see a piece of content, returns a
*reason* rather than a boolean, and is the only implementation in the system:

```python
entitlements.services.resolve_access(user, lesson) -> AccessDecision
```

Everything else in M4 exists to feed it or to enforce its answer.

---

## 2. What M4 is not

- **Not billing.** No prices, no invoices, no payment methods, no tax, no
  currency. The payment provider decision is open (CLAUDE.md §11 #1) and the
  standing rule holds: **do not model billing.**
- **Not the trial lifecycle.** M9 owns trial creation, abuse prevention and
  expiry sweeps. M4 only has to *resolve* a subscription that is already
  `TRIALING`.
- **Not webhooks.** M8. The fake provider is driven by management commands.
- **Not media.** M5 owns playback tokens. M4 gates a lesson *detail* endpoint;
  the token endpoint arrives with the media pipeline and calls this resolver.

---

## 3. Decisions

Four were raised. **All four are settled** (2026-08-18). Recorded in
`docs/adr/010-m4-entitlement-decisions.md`.

| # | Decision | Outcome |
|---|---|---|
| 3.1 | `Plan` model in M4 | **No.** Deferred to M8. |
| 3.2 | Trial scope | **Preview lessons only.** No new schema. |
| 3.3 | `PAST_DUE` grace period | **7 days**, as a named setting. |
| 3.4 | Cache the resolver in M4 | **No.** Added in M8 with its invalidation source. |

### 3.1 Does M4 ship a `Plan` model? — **settled: no**

`architecture.md` §10 M4 lists `Subscription`, `Plan`, `AccessOverride`. But
CLAUDE.md §3 says **a single subscription tier**, monthly or yearly. With one
tier, entitlement never asks *which* plan — access is decided by subscription
*status*, not by plan identity. Everything a `Plan` row would carry (price,
interval, currency, provider price id) is billing, which is the thing I am
told not to model.

This is a document/code disagreement of the kind §9 says to report rather than
resolve silently. **Settled: `Plan` is deferred to M8**, recorded in ADR-010 as
an amendment to the milestone definition in `architecture.md` §10.

If a second tier is ever planned, that reopens this: it changes the resolver
from "is the subscription live" to "does this subscription cover this content",
which is a different function with a different signature.

### 3.2 What does a trial grant? — **settled: preview lessons only**

A trial is scoped, and the scope is the set of lessons already flagged
`is_preview`. No new schema: no eligibility flag on `Course`, no relation on
`Subscription`, no lesson quota — and therefore no dependency on the progress
tracking that does not exist until M7.

**The consequence, recorded so nobody rediscovers it as a bug.** Branch 1 of
the resolver already allows preview lessons to *everyone*, including anonymous
visitors. So a `TRIALING` subscription grants no content that an unauthenticated
browser cannot already reach. `TRIALING` is, for gated content, a **denial
branch that carries a better reason** — `TRIAL_SCOPE` with `cta=upgrade`
rather than the anonymous `cta=subscribe`.

That is a coherent thing to ship: it keeps the subscription lifecycle real and
exercised end to end before M8 touches it, and it gives M9 a state to build
on. It is *not* a trial that converts by showing paid content. **If conversion
is the goal, the mechanism needs revisiting in M9** — most likely as the
per-course eligibility flag considered and set aside here.

### 3.3 How long is the `PAST_DUE` grace period? — **settled: 7 days**

A business decision with direct revenue consequences in both directions: too
short and a failed card locks out a paying customer mid-lesson; too long and
access is free after payment stops. I will not invent it.

**Settled: 7 days**, as a named setting (`ENTITLEMENT_GRACE_PERIOD`) rather
than a literal, so changing it is a config change and the boundary is
testable. Long enough for a card retry cycle.

### 3.4 Is the resolver cached in M4? — **settled: no**

§4.5 rule 3 says "cached in Redis with a short TTL, invalidated on every
webhook". **There are no webhooks until M8.** A cache whose invalidation
source does not exist yet can only expire by TTL, which means a cancelled
subscription keeps access until the TTL lapses — a caching bug that hands out
the product, introduced before anything needs the cache.

**Settled: build the resolver uncached**, pin its query cost with an ADR-009
test, and add caching in M8 alongside the webhook that invalidates it. The
resolver's signature does not change, so this costs nothing later.

---

## 4. Model sketch

Nothing here is provider-specific beyond two opaque strings, which is
invariant 7's pattern applied to billing: store `provider` and the provider's
id, never the provider's object model.

**`Subscription`** — one live row per user, enforced in the database.
`user` (FK), `status`, `current_period_end`, `trial_end` (nullable),
`cancel_at_period_end`, `provider`, `provider_subscription_id` (nullable until
M8; unique per provider when set).
Statuses: `TRIALING`, `ACTIVE`, `PAST_DUE`, `CANCELED`, `EXPIRED`.

**`SubscriptionEvent`** — append-only, the same shape M3 proved with
`CourseReviewEvent`: a mutable `status` says what is true now and cannot answer
why someone's access is wrong six weeks later (§5.2).

**`AccessOverride`** — a first-class, time-bounded row with `granted_by`,
`reason`, `starts_at`, `ends_at` — never a boolean on `User`. §5.2 is explicit:
a flag is permanent, unexplained, and nobody dares remove it.

**Constraints in the database, not only in Python** (invariant 11):
a partial unique index giving each user at most one non-terminal subscription;
a check that `TRIALING` implies `trial_end IS NOT NULL`; a check that
`ends_at > starts_at` on overrides.

---

## 5. The resolver

Signature takes a `Lesson`; the course and its instructor come from it.
CLAUDE.md invariant 3 writes `content` and §4.5 writes `lesson` — same
function, and I will use `lesson` with the wider name kept free for M7.

Order of evaluation, from §4.5, each branch returning a distinct reason:

1. `lesson.is_preview` → **allow**, `reason=PREVIEW`, no authentication needed
2. anonymous → **deny**, `reason=LOGIN_REQUIRED`, `cta=login`
3. admin, or the course's instructor → **allow**, `reason=OWNER` / `STAFF`
4. active `AccessOverride` covering now → **allow**, `reason=OVERRIDE`
5. subscription `ACTIVE` → **allow**
6. `TRIALING` → gated content is out of scope (§3.2) → **deny**,
   `reason=TRIAL_SCOPE`, `cta=upgrade`. Preview lessons never reach this
   branch; branch 1 allowed them already.
7. `PAST_DUE` within grace → **allow**, `reason=GRACE`; past it → **deny**
8. `CANCELED` before `current_period_end` → **allow**; after → **deny**
9. `EXPIRED`, or no subscription → **deny**, `cta=subscribe`

`AccessDecision` is a frozen dataclass: `allowed`, `reason`, `cta`. Denials
surface as **403 Problem Details with a stable `type` URI**, per ADR-004 —
clients branch on `type`, never on the status code, and `reason`/`cta` ride as
extra members.

---

## 6. Abuse cases — these become the first tests

1. Anonymous request for a gated lesson → 403 `LOGIN_REQUIRED`, never the body.
2. Authenticated user with **no** subscription → 403, and the lesson body is
   absent from the response, not merely flagged.
3. Subscription `EXPIRED` one second ago → denied. Boundary tested exactly.
4. `CANCELED` with `current_period_end` in the future → **allowed**; one second
   after → denied.
5. `PAST_DUE` at the grace boundary → allowed at the edge, denied past it.
6. An override that expired yesterday → denied. An override starting tomorrow →
   denied.
7. A user cannot read another user's subscription or override through any
   endpoint → 404, not 403 (§6.3).
8. `is_preview` on a lesson is not writable by an instructor via any public
   field — a self-granted preview flag is a self-granted giveaway.
9. **The resolver is actually called.** A gated endpoint that forgets to call
   it returns content; the test asserts denial through the endpoint, not by
   unit-testing the function.
10. **Nothing else re-derives access.** A grep-style test asserting no
    `status == "ACTIVE"` comparison exists outside `entitlements/`.

Case 10 is the invariant-3 guard. Cases 3–6 are the boundaries §4.5 rule 4
names.

---

## 7. Coverage and verification

- **100% branch on the resolver.** CLAUDE.md §8 requires it; enforced in CI,
  not merely reported.
- **ADR-006:** each control provoked. For the fake provider, that means driving
  a subscription into each state through the management command and observing
  the endpoint's answer change — not asserting the model field.
- **ADR-009:** the resolver runs on the hottest path in the product. Query cost
  measured at two dataset sizes and pinned.
- **Never mock our own service layer and assert it was called** (CLAUDE.md §6).
  The fake provider is a real adapter behind the §4 interface, driven by
  management commands, exactly as §10 M4 specifies.

---

## 8. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR for §3 decisions | approval |
| T2 | `Subscription`, `SubscriptionEvent`, `AccessOverride` + constraints | T1 |
| T3 | Fake billing provider behind an adapter + management commands | T2 |
| T4 | `resolve_access` + `AccessDecision`, 100% branch | T2 |
| T5 | Problem Details type for entitlement denial; DRF permission class | T4 |
| T6 | Gated lesson detail endpoint wired to the resolver | T5 |
| T7 | `GET /auth/me/` returns the decision so the frontend never re-derives it | T4 |
| T8 | Admin diagnostics: subscription state, event log, entitlement trace | T4 |
| T9 | Boundary and abuse-case tests; query cost pinned | T6 |
| T10 | Schema, types, ADRs | T9 |

---

## 9. Invariants this touches

3 (one resolver, returns a reason, never a stored `has_access`), 2 (layering —
no access logic in serializers or views), 10 (every queryset scoped), 11
(constraints in the database), 4 (the fake provider sits behind an adapter),
16 (types regenerated).
