# M10 — Admin & Moderation

**Status:** complete. All ten tasks shipped; see `docs/STATUS.md`.
**Branch:** `feat/m10-admin`
**Depends on:** M3 (review queue), M4 (`AccessOverride`, diagnostics)

---

## 1. Objective

**An admin can resolve any access complaint without touching the database** —
and every action they take to do it is recorded.

Two halves, and the second is the one that makes the first safe. M10 hands a
small number of people the ability to grant free access and issue refunds. That
capability without a trail is indistinguishable from a compromise.

---

## 2. Decisions — settled 2026-08-21

| # | Decision | Outcome |
|---|---|---|
| 2.1 | Django admin site | **Routed, with mandatory TOTP 2FA.** |
| 2.2 | Refund action | **Service and audit only**, no provider call. |
| 2.3 | How audit rows are written | **Explicitly, in the service.** |
| 2.4 | Review-queue API | **Deferred**, declining §6.10 for now. |
| 2.5 | Frontend | **None.** Backend and Django Admin only. |

### 2.1 Routing the admin site — **settled: yes, behind 2FA**

§8 is unambiguous: *"Django Admin is production infrastructure and must be
secured like it… non-obvious URL path, staff-only, mandatory 2FA
(`django-otp`), IP allow-list if practical, and every action audit-logged."*

It has been deliberately unrouted since M0 precisely so this milestone could do
it properly. Routing it is what makes M3's review queue usable and what makes
the objective reachable.

**New dependencies, approved:** `django-otp` and `qrcode` (for enrolment QR
codes). Both are free and add nothing to the monthly bill. To be confirmed
against actual package versions at T6 rather than pinned from memory.

**An IP allow-list is not in scope.** The operator is in Morocco on a
residential connection and the hosting target is undecided (§11 #4); an
allow-list written now would be a guess that locks somebody out. Recorded as a
M13 consideration.

### 2.2 Refunds — **settled: everything except the money movement**

§10 M10 names a refund action, and M8 — the milestone that integrates a payment
provider — is blocked on the provider decision (§11 #1).

**What M10 builds:** the permission check, the service, the audit row, and the
refusal cases. **What it does not build:** a provider call.

The reason is §6: *never invent a provider capability*. Refund semantics differ
materially between providers — partial refunds, refund windows, whether an
idempotency key is required, whether a refund is synchronous or an event that
arrives by webhook. Writing a plausible one and testing against it would
manufacture confidence in behaviour nobody has verified. M4's precedent —
build against a fake — holds for *entitlement*, where we own the rules; it does
not hold for a provider's refund API, where we do not.

The service raises `RefundNotAvailable` until M8 supplies the adapter. The test
asserts that, so the gap is visible rather than silent.

> **Amended at T8.** "The audit row" above did not survive implementation, and
> the decision above is left as written because it is the record of what was
> settled on 2026-08-21. A refund that raised did not happen, and a row
> describing an action that did not happen is a false record — the line this
> suite already holds for a rejected course approval. `REFUND_ISSUED` stays in
> the closed vocabulary as the marker and M8 makes it reachable. ADR-019 §2.

### 2.3 Audit rows are written explicitly — **settled**

`record_admin_action(...)`, called in the service beside the write, inside the
same transaction.

Signals were the alternative and are worse here: they fire for writes that are
not administrative, cannot see *who* acted or *why*, and put the audit trail
somewhere nobody looks when reading the code that performs the action.
Middleware over `/admin-api/` catches what a service forgets, but records HTTP
shape rather than domain meaning — "POST returned 200" is not "granted 14 days
of access because the learner was double-charged".

**The forgettability problem is real and is answered with a guard**, not with
cleverness: a structural test asserting every mutating admin surface writes an
audit row, provoked before it is trusted.

### 2.4 The review-queue API is deferred — **declining §6.10 for now**

§6.10 lists `GET review-queue/` and `POST courses/{id}/review/`. M3 already
built both as Django Admin actions, tested, with a `CourseReviewEvent` trail.
The API exists to serve a custom admin UI, and there is no admin UI — building
it now is an endpoint with no caller, which §5 calls working ahead.

**What M10 does instead:** makes the existing review actions write audit rows,
so approval is covered by §8 regardless of which surface performs it.

### 2.5 No frontend

Explicitly out of scope at the owner's instruction. Django Admin is the
interface for this milestone.

---

## 3. Model sketch

**`AuditLog`** — `actor`, `actor_label`, `action`, `target_type`, `target_id`,
`metadata` (JSONB), `ip_address`, `created_at`. Index on
`(target_type, target_id, -created_at)`, which is §5's stated question: *"what
happened to this user?"*

Two details that are decisions rather than transcription:

- **`actor` is `SET_NULL`, with `actor_label` captured at write time.** A
  `PROTECT` makes an audit row block account deletion forever, which collides
  with erasure obligations; a bare `SET_NULL` loses accountability the moment an
  admin account is removed. Storing the label denormalised keeps the trail
  readable after the foreign key is gone. This is the one place in the codebase
  where denormalisation is correct: the value is a *historical fact*, not a
  cache of something still changing.

- **Append-only, enforced where it can be.** No service updates or deletes a
  row; the model is registered read-only in the admin with add, change and
  delete permissions all denied. This is not tamper-*proof* — a database
  superuser can do anything — and the spec says so rather than implying a
  guarantee it cannot make. Cryptographic chaining is out of scope and would be
  security theatre without an external witness.

**`AccessOverride` already exists** (M4) and is already read by the resolver.
M10 adds the *write* path it never had. An override without an expiry is not
accepted: §5 models it as time-bounded specifically so it cannot become "a
permanent unexplained flag that nobody dares remove".

**`CourseReviewEvent` is not replaced.** It is the course's own history, shown
to the instructor who submitted it. `AuditLog` is the cross-cutting
administrative trail, read when answering "what did we do to this account".
Both rows get written on an approval, and that is not duplication — they answer
different questions for different readers.

---

## 4. Abuse cases — these become the first tests

1. A non-admin reaching any `/admin-api/` route is refused — **swept over every
   routed endpoint**, not asserted per route. An ordinary user reaching the
   admin site is not told it exists. (The second half is **not met** and is
   recorded as a known limit in ADR-019 §5: a visitor who finds the path sees
   Django's login form. The controls that operate are the unguessable path,
   `is_staff`, and mandatory TOTP.)
2. An admin **without a confirmed 2FA device** cannot reach the admin site,
   even with correct credentials.
3. An access override **without an expiry or a reason** is refused.
4. An **expired** override grants nothing — proven through the new write path,
   end to end, not only at the resolver.
5. Every mutating admin surface writes **exactly one** audit row, carrying
   actor, target, reason and IP. Structural guard.
6. An audit row cannot be edited or deleted through any surface we ship.
7. An audit row **survives deletion of its actor**, still naming who acted.
8. Diagnostics leaks nothing to a non-admin — not to a student, an instructor,
   or a `is_staff` account without `role == ADMIN`. **Provider identifiers stay
   in the response for administrators**, deliberately: `provider_subscription_id`
   is the handle support needs to find the same subscription in the provider's
   own dashboard, and this endpoint is administrators only. (Reworded at T10.
   The original sentence read as though the field had to go, which contradicted
   M4's serializer and its written rationale. ADR-019 §6.)
9. The admin path appears in **no response body and no OpenAPI schema** —
   asserted against raw bytes, swept rather than spot-checked.
10. An admin granting an override **to themselves** is recorded exactly like
    any other grant. Deliberately not blocked: an admin who wants free access
    can grant it to a second account, so blocking is theatre — the control that
    works is the one that makes it visible.

---

## 5. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR-018 | approval |
| T2 | `AuditLog` model, index, append-only | T1 |
| T3 | `record_admin_action` service + structural guard | T2 |
| T4 | Access override write path, audited | T3 |
| T5 | Route the Django admin: obscure path, staff-only | T1 |
| T6 | 2FA: `django-otp` enrolment and enforcement | T5 |
| T7 | Audit the existing admin actions (approval, role change) | T3, T5 |
| T8 | Refund service and audit, no provider call | T3 |
| T9 | Audit log read surface + diagnostics extension | T4, T7 |
| T10 | Abuse cases, schema, types, ADR-019, close-out | all |

---

## 6. Not in M10

- **No refund provider call.** §2.2. M8.
- **No review-queue API.** §2.4.
- **No admin frontend.** §2.5.
- **No IP allow-list.** §2.1 — M13, when the hosting target is known.
- **No cryptographic tamper-evidence** on the audit log. §3.
- **No user deletion or data-export flow.** Erasure obligations are real and
  are their own piece of work; `actor_label` is here so the audit trail is
  ready for it, not because M10 implements it.
