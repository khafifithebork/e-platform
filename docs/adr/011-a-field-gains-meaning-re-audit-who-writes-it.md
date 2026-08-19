# ADR-011 — When a field gains meaning, re-audit who can write it

**Status:** Accepted
**Date:** 2026-08-19
**Context:** M4 — Entitlements. Third in the family that began with ADR-006
(provoke the control) and ADR-009 (measure, do not reason). This one is about
a failure that is invisible at the time it is introduced.

---

## 1. What happened

M3 added `Lesson.is_preview` and exposed it as a writable field on the
instructor lesson API. That was reviewed and looked fine, because it *was*
fine: nothing read the field. An instructor setting it changed nothing
observable.

M4 made `is_preview` the entitlement resolver's **first branch** — allowed
before the caller is even identified, so a preview lesson is readable by
anyone on the internet. The same writable field became a switch an instructor
could use to publish a whole course for free. Since the subscription is shared
across the catalogue, that is not an instructor giving away only their own
work; it is revenue taken from everyone.

Nothing changed in M3's code. Its permissions were not weakened. **The field
acquired a meaning that its write permissions had never been chosen for.**

Caught by writing spec §6's abuse case 8 as a test, four months of milestones
after the field was introduced.

---

## 2. Why the usual defences miss it

- **Code review** saw a boolean on a content model. There was no rule to
  violate yet.
- **ADR-006** demands that a control be provoked. There was no control.
- **Tests** passed, correctly, at both ends: M3's tests asserted the field
  round-tripped, and M4's asserted the resolver honoured it.

The two changes are individually correct and jointly a bypass. No test that
looks at one milestone can see it.

---

## 3. The rule

**When a field starts being read by an access, billing or security decision,
re-audit every path that can write it — in the same change.**

Concretely, when adding a read of an existing field to a rule that grants or
denies something:

1. List every serializer, form, admin and management command that can write it.
2. For each, ask whether *that* writer should be able to influence *this*
   decision.
3. Where the answer is no, make it read-only there, and write the test that
   fails if it becomes writable again.
4. Confirm the capability still exists somewhere it belongs. A field nobody
   can set is a feature quietly deleted — `is_preview` moved to admins, it did
   not disappear, and a test asserts that.

This is cheap. It is a grep and a judgement per writer, done once, at the
moment the field stops being decorative.

---

## 4. Where this bites next

Every milestone from here adds meaning to fields that already exist:

- **M5** — `MediaAsset` status decides whether a playback token is minted.
  Anything an instructor can write that feeds that decision needs this pass.
- **M8** — `Subscription.provider_subscription_id` becomes the webhook lookup
  key. It is admin-invisible and service-written today; when a webhook trusts
  it, check nothing else can set it.
- **M9** — `trial_end` starts bounding a self-serve trial rather than a
  command-issued one. ADR-010 §2 already flags that `trial_covers` must be
  narrowed before then; this is the same audit from the other direction.

---

## 5. What this does not ask for

Not a ban on writable fields, and not a review of every field on every change.
The trigger is narrow and specific: **a decision that grants or denies
something starts reading a field it did not read before.** That is the moment,
and it is usually a one-line diff in a resolver — which is exactly why it does
not feel like a permissions change.
