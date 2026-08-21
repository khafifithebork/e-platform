# ADR-018 — M10 admin: the trail is the control

**Status:** Accepted
**Date:** 2026-08-21
**Spec:** `docs/specs/m10-admin.md`

---

## 1. Why this milestone needs an audit log before it needs anything else

M10 hands a small number of people the ability to **grant free access and issue
refunds**. §8 already says every such action must be recorded. The reason to
state it again here is ordering: the audit log is not a reporting feature to add
once the admin tools work, it is the thing that makes shipping them acceptable.

So `AuditLog` is T2 and `record_admin_action` is T3, before the first capability
that would need auditing exists. Build the trail, then build the thing that
walks on it.

**The failure this avoids** is specific: an admin capability shipped in one task
and audited in a later one is unaudited in production for however long the gap
lasts, and the rows for that period never come back.

---

## 2. Routing the Django admin, with 2FA

**Decision.** Route it at a path read from the environment, staff-only, with
mandatory TOTP via `django-otp`.

**Why now.** It has been unrouted since M0 with a comment saying M10 would
harden it. M3's review queue is unusable until it is routed, and the
milestone's deliverable — resolve any access complaint without touching the
database — is unreachable without it.

**Why 2FA is not deferrable to M12.** Routing is what creates the exposure. A
milestone that routes the highest-value target in the system and defers its
stated control has moved the risk forward and the mitigation back. If 2FA were
not going to land here, the honest choice would be to leave the site unrouted.

**Dependencies approved:** `django-otp`, `qrcode`. Versions are to be read from
the actual packages at T6, not written from memory — §6 forbids inventing
capabilities, and a version number recalled rather than checked is the same
mistake in smaller form.

**Not in scope: an IP allow-list.** §8 says "if practical". It is not: the
operator's connection is residential and the hosting target is undecided
(§11 #4). An allow-list guessed now is a lockout waiting to happen.

---

## 3. Refunds: everything except the money

**Decision.** M10 builds the permission check, the service, the audit row and
the refusal paths. It does not call a provider. The service raises
`RefundNotAvailable` until M8 supplies an adapter, and a test asserts exactly
that.

**Why this is not the same as M4.** M4 built entitlements against a fake billing
provider and that was right, because the *rules* being tested were ours —
what an expired subscription grants is a decision this codebase makes. A
refund's semantics belong to the provider: whether partial refunds exist,
whether there is a window, whether an idempotency key is mandatory, whether the
result is synchronous or arrives later by webhook. Writing a fake that answers
those questions invents a provider capability, and every test against it would
be confidence in something nobody has verified.

**What is gained by building the rest now.** The permission boundary and the
audit row are ours, they are testable, and they are the parts that must not be
bolted on hastily later beside a live payments integration.

**The visible gap is deliberate.** A test asserting `RefundNotAvailable` is a
marker that reads as unfinished, because it is.

---

## 4. Audit rows are written by hand, and a guard catches the ones that are not

**Decision.** `record_admin_action(...)` is called explicitly in each service,
in the same transaction as the write it describes.

**Why not signals.** They fire for writes that are not administrative, they
cannot see the actor or the reason, and they hide the trail from the code that
performs the action. An audit entry whose *why* field is always empty is a log,
not an audit.

**Why not middleware.** It cannot record domain meaning. "POST /access-override/
returned 200" is not "granted fourteen days because the learner was
double-charged", and the second is the only one worth keeping.

**The obvious objection — somebody will forget — is answered with a test**, not
with a mechanism: a structural guard asserting every mutating admin surface
writes a row, provoked by removing one call before it is trusted. This is
ADR-006 again, and it is the pattern that has caught the most in this codebase:
M7 shipped two guards that passed with the control removed, and both were found
by trying it.

---

## 5. `actor` is nullable, and the label is kept beside it

**Decision.** `AuditLog.actor` is `SET_NULL`, with `actor_label` written at the
time of the action.

**Why not `PROTECT`.** An audit row would then block deletion of an admin
account forever. Erasure obligations are real, and a design that makes the audit
log the reason a person cannot be removed will eventually be resolved by
deleting audit rows — the worst possible outcome for the thing whose only job is
to be complete.

**Why not a bare `SET_NULL`.** Accountability vanishes the moment an
administrator leaves. "Somebody granted this person free access" is not an audit
trail.

**Why the denormalisation is correct here**, when §5.2's own advice is that
denormalised values drift: this one cannot. It is a historical fact about a
moment, not a cached copy of something that is still changing. That is the test
for when denormalisation is right, and it is worth naming because the same
reasoning was used to *decline* denormalisation in ADR-016 §3.

---

## 6. What "append-only" does and does not mean here

**Decision.** No service updates or deletes an audit row, and the model is
registered in the admin with add, change and delete all denied.

**What this is not.** It is not tamper-proof. A database superuser can rewrite
anything, and cryptographic chaining without an external witness proves nothing
that a determined operator cannot reproduce. Claiming otherwise would be
security theatre, and the spec says so plainly so that nobody later reads a
guarantee into it that was never there.

**What it does buy.** No *application* path edits history, which is the class of
accident and the class of compromise the application layer can actually prevent.
Everything beyond that is a database-permissions and backup-integrity question,
and it belongs to M13 and M14 where those exist.

---

## 7. Declining §6.10's review-queue API, for now

**Decision.** M10 does not build `GET review-queue/` or
`POST courses/{id}/review/`.

**Why.** M3 already built both as tested Django Admin actions with a
`CourseReviewEvent` trail. The API in §6.10 exists to serve a custom admin UI
that does not exist and is not scheduled. An endpoint with no caller is working
ahead (§5), and it would need rewriting once a real interface had opinions.

**What M10 does instead.** The existing review actions write audit rows, so §8's
requirement that course approval be audited is met by the surface that actually
performs approvals.

**This is a deferral, not a rejection**, and it is recorded so the mismatch
between the document and the code is not read later as an oversight.

---

## 8. `CourseReviewEvent` and `AuditLog` both exist, on purpose

They answer different questions for different readers. `CourseReviewEvent` is
part of a course's own history and is shown to the instructor who submitted it:
*what happened to my course, and what was I asked to change*. `AuditLog` is the
administrative trail, read while answering a support ticket: *what have we done
to this account, and who did it*.

Collapsing them would mean either showing instructors the administrative log or
scattering course history across a generic table with a JSON blob. Two narrow
tables beat one wide one whose rows mean different things depending on a type
column.
