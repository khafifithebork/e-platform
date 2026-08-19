# ADR-010 — M4 entitlements: the decisions the resolver rests on

**Status:** Accepted
**Date:** 2026-08-19
**Amends:** `architecture.md` §10 M4 (see §1) and §4.5 rule 3 (see §4).
**Context:** M4 — Entitlements. CLAUDE.md §9 names this the most expensive
place in the codebase to guess, and §5 gates the entitlement model on explicit
approval. Four decisions were put to the owner before any code was written;
three were settled, one remains open and is recorded in §2.

---

## 1. No `Plan` model in M4 — deferred to M8

**Decision.** `Subscription`, `SubscriptionEvent` and `AccessOverride` ship.
`Plan` does not.

**Why.** `architecture.md` §10 M4 lists `Plan` among the objectives, but
CLAUDE.md §3 describes **a single subscription tier**. With one tier,
entitlement never asks *which* plan — access is decided by subscription
*status*. Everything a `Plan` row would carry (price, interval, currency,
provider price id) is billing, and the standing rule while the payment
provider is undecided is that billing is not modelled.

**This amends the milestone definition.** Recorded rather than done silently,
per §9: a document and the plan disagreed.

**Reopen if** a second tier is ever planned. That changes the resolver from
"is this subscription live" to "does this subscription cover this content",
which is a different function with a different signature.

---

## 2. A trial is scoped — **the scoping rule is still open**

**Decided.** A trial grants *less* than a paid subscription. The §4.5
flowchart's `TRIALING → Trial grants this course?` branch is real.

**Not decided.** What scopes it. A flag on `Course`, a relation on
`Subscription`, and a count of consumed lessons are three different schemas,
and the last needs progress tracking that does not exist until M7.

**What shipped.** The branch exists and is isolated in one function,
`entitlements.resolver.trial_covers`, which currently grants what an active
subscription grants. A test fails if the trial branch grows a second decision
point, and the `TRIAL_SCOPE` denial is covered by substituting a refusing rule
so the branch is not untested.

**Why that is safe today, and exactly when it stops being.** There is **no
self-serve trial**: a subscription can only be started by the `billing`
management command, so nobody can grant themselves a trial to exploit the
permissive default. **The moment M9 adds a self-serve trial, this becomes a
way to get the catalogue free.** M9 must not ship before §3.2 is answered.

---

## 3. `PAST_DUE` keeps access for 7 days

**Decision.** `ENTITLEMENT_GRACE_PERIOD_DAYS`, default 7.

**Why a grace period at all.** A failed card is usually an expired card, not a
decision to stop paying. Cutting access instantly punishes the customer for
their bank's timing.

**Why 7.** Long enough for a typical retry cycle. A business decision with
revenue consequences in both directions, taken by the owner rather than
invented.

**Why a setting.** So the boundary is a value a test can move, and changing it
is configuration rather than a code change. A literal would have made
`test_the_grace_period_honours_the_setting` pass by coincidence at the
default.

**Measured from the end of the unpaid period**, not from when the charge
failed. A card can fail days before a period ends, and grace is meant to start
when access would otherwise stop.

---

## 4. The resolver is not cached in M4 — amends §4.5 rule 3

**Decision.** `resolve_access` reads the database on every call. No Redis, no
TTL.

**Why.** §4.5 rule 3 asks for "a short TTL, invalidated on every webhook".
**There are no webhooks until M8.** A cache whose invalidation source does not
exist can only expire by timeout, so a cancelled subscription would keep
access until the TTL lapsed — a caching bug that gives the product away,
introduced before anything needed the cache.

**What replaces it for now.** The query cost is pinned instead (ADR-009): two
queries, constant as a user's subscriptions accumulate, and zero for a preview
lesson.

**When it arrives.** M8, alongside the webhook that invalidates it. The
signature does not change, so this costs nothing later. The strongest argument
for it is `/auth/me/`, which the frontend calls on load and after every auth
transition, and which now costs five queries instead of three.

---

## 5. Visibility and entitlement are separate gates

**Decision.** The gated lesson endpoint runs `lessons_visible_to` **and**
`IsEntitledToLesson`, in that order, answering two different questions.

**Why.** `resolve_access` knows about subscriptions, not publication. A paying
subscriber passes its `SUBSCRIPTION_ACTIVE` branch on a lesson in an
unpublished course and reads a draft the instructor never submitted. The
resolver is not wrong to allow it — it was never asked about publication.

Merging them would put catalogue rules inside the resolver and course status
into a function that is only about subscriptions. Keeping them apart means an
unpublished lesson is a **404** (it does not exist for you, §6.3) while an
ungated one is a **403 with a reason**.

---

## 6. One problem type, many reasons

**Decision.** Every entitlement refusal is `403` with
`type: /problems/entitlement-denied` and a `reason` from a stable enum.

**Why not a type per reason.** Clients branch on `type` (ADR-004). A type per
reason makes every new reason a breaking change for anything matching on
unknown types.

**Why 403 even for `LOGIN_REQUIRED`.** §6.3 specifies 403 for entitlement
denial, and DRF downgrades 401 to 403 anyway when no authenticator offers a
`WWW-Authenticate` header — `SessionAuthentication` offers none. The status
would be 403 whatever we intended.

**Consequence.** `reason` and `cta` are API contract. Renaming one breaks the
frontend, so they are asserted literally in tests rather than compared against
the enum that produces them.

---

## 7. `ACTIVE` does not check the period end

**Decision.** An `ACTIVE` subscription grants access regardless of
`current_period_end`, following §4.5's flowchart.

**The trade-off, stated plainly.** A stale `ACTIVE` row past its period grants
free access until something expires it. The alternative — denying on a past
period — locks out a paying customer whenever a renewal event is late, which
is both likelier and worse.

**What closes the exposure.** M9's expiry sweep. Until it exists, an `ACTIVE`
subscription nobody expires is access nobody revokes.

---

## 8. Manual access is granted in one place only

**Decision.** `AccessOverride` can be created **only** through Django Admin.
No endpoint, no management command. `granted_by` comes from the session and
the field is not rendered.

**Why.** §5.2 wants a table rather than a flag so a grant says who made it and
expires by itself. A grant attributable to somebody else, or editable
afterwards, gives that up. Extending access means granting another override,
leaving both on the record.

**Consequence.** Overrides are unreachable until M10 routes the admin site
(ADR-008 §5). That is accepted: no production data exists yet, and a support
tool that cannot be reached is better than a grant surface that is not
hardened.

---

## 9. What M4 did not do

- **No billing.** No prices, no invoices, no payment methods, no tax. The
  payment provider decision is still open and blocks M8 entirely.
- **No trial lifecycle.** M9 owns creation, abuse prevention and expiry
  sweeps — including the expiry that §7 depends on.
- **No webhooks.** M8. The fake provider is driven by management commands.
- **No playback tokens.** M5. The token endpoint calls this resolver; §4.5's
  rule that the check and the mint live in one service function, in that
  order, is M5's to keep.
- **No lesson list endpoint.** Object-level permissions cannot gate a
  collection. Anything returning many lessons must run the resolver per row or
  filter by a second access rule, and the second rule is the one that drifts.
