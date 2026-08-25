# ADR-019 — M10 admin: what implementation settled

**Status:** Accepted
**Date:** 2026-08-25
**Spec:** `docs/specs/m10-admin.md`
**Decisions before code:** `docs/adr/018-m10-admin-decisions.md`

ADR-018 recorded what M10 decided before writing any of it. This records what
writing it changed, what it found already broken, and the three things it is
handing to later milestones.

---

## 1. A decision recorded in an ADR is not a control until something asserts it

**This is the standing rule from M10, and it is worth reading before the next
milestone writes an ADR.**

ADR-018 §6 said, in accepted prose: `AuditLog` "is registered read-only in the
admin with add, change and delete permissions all denied". T2 shipped the model
and never registered it anywhere. Nothing noticed for seven tasks, because
abuse case 6 — *an audit row cannot be edited or deleted through any surface we
ship* — **passed the whole time**. There was no surface. The test was true and
meaningless, and the ADR read as though the work were done.

This is ADR-006's shape one level up. ADR-006 says a security control nobody
has provoked may be inert. This says the same of a control nobody has
*written*: an accepted decision creates the impression of a control, and the
impression survives review indefinitely because the reviewer is reading the
document that promised it.

**The rule:** when an ADR says a mechanism exists, the task that accepts the
ADR either builds it or names the task that will. A decision with no owner and
no failing test is a plan, and plans do not defend anything.

---

## 2. The refund refuses, and writes nothing — including no audit row

ADR-018 §3 settled that M10 builds everything except the provider call. Spec
§2.2 also put "the audit row" in scope, and implementation could not honour
that honestly.

**A refund that raised `RefundNotAvailable` did not happen, and a row
describing an action that did not happen is a false record.** The suite already
refuses that shape for a rejected course approval
(`test_a_refused_approval_writes_nothing`), and money is not the place to
weaken it. `REFUND_ISSUED` stays in `AdminAction` as the marker; M8 is what
makes it reachable.

**The alternative was rejected on ADR-018 §3's own reasoning.** A `refund()`
method on the provider protocol, proven against a test stub, would have made
the audit path reachable — by inventing the capability that ADR forbids by
name: whether partial refunds exist, in what currency, within what window,
whether an idempotency key is mandatory, whether the result arrives by webhook.

**501, not 503.** A 503 tells a client to try again shortly; nothing about
waiting integrates a payment provider. It carries its own problem type, because
ADR-004 has clients branch on the type and a bare 501 would be
indistinguishable from anything else the server later grows.

**No amount in the request.** `Subscription` holds no money by design, and
partial-refund semantics are a provider fact this project does not have. The
field arrives with M8, shaped by what the provider actually does.

---

## 3. A route inventory needs two sets, not one

T4 shipped a guard enumerating every mutating `/admin-api/` route and asserting
each is declared audited. T8's refund route is mutating in shape and performs
no mutation, so declaring it audited would have put a false entry in the one
table that must not contain one.

The guard now holds `AUDITED` and `NOT_YET_CAPABLE`, and a route in the second
is tested to actually refuse and actually record nothing. **M8 must move the
refund across**, and the guard fails until it does — which is the difference
between a follow-up somebody remembers and a follow-up the build enforces.

---

## 4. The trail has two readers, and they render different things

**The admin site is the surface for detail.** The whole row, `metadata`
included, read-only, searchable, paginated.

**Diagnostics is the surface for the question support arrives with** — *what
did we do to this account recently, and who did it*. It renders `action`,
`actor_label`, `reason` and `created_at`, and **deliberately not `metadata`**.
The blob is open-ended and written by every service that records an action, so
an endpoint returning it wholesale publishes whatever a future
`record_admin_action(..., something=...)` puts there, with no review against
the serializer that exposes it. `reason` is lifted out by name because §8
requires it.

**User-targeted rows only.** Overrides and role changes target the user; a
course approval targets the course, and a refund will target the
*subscription*. **M8 must revisit `admin_trail_for`**, or the first real refund
will be absent from the exact screen somebody opens to ask about it. Joining
through every object a user owns was declined now because T8 makes a refund
impossible and the join would be a path no test could reach.

**Capped at fifty, with the true total beside it.** A list capped at fifty that
reported fifty as its total would tell support they had seen everything, which
is the one thing a truncated audit view must not do.

`actor_label` is what the API renders, not a nested actor — the column exists
so the row stays readable after the account is gone, and a serializer reading
`actor.email` would return null exactly when the trail matters most.

---

## 5. Abuse case 1's second half is not met, and the spec should say so

Case 1 reads: *"an ordinary user reaching the admin site is not told it
exists."* **It is not.** A non-staff visitor who finds the path gets Django's
admin login form, which identifies itself unambiguously.

**Recorded as a known limit rather than fixed**, on the owner's decision. The
controls that actually operate are the unguessable path (checked by
`core.E001`, which refuses `admin`, `dashboard` and friends), `is_staff`, and
mandatory TOTP. "Not told it exists" is met by obscurity alone, and obscurity
is worth exactly as much as the path staying unknown — which is why abuse case
9 is swept rather than spot-checked.

Making `HardenedAdminSite` answer 404 to unauthenticated requests is a
defensible follow-up. It is a behaviour change to a routed production surface
and did not belong in a milestone's closing task.

---

## 6. Abuse case 8 said something it did not mean

Spec §4 case 8 said diagnostics must leak "no provider identifiers".
`SubscriptionDiagnosticSerializer` has carried `provider_subscription_id`
since M4 on purpose: it is the handle support needs to find the same
subscription in the provider's own dashboard, on an administrators-only
endpoint.

**Settled: the sentence is about what a non-admin can learn, and the field
stays.** The spec is reworded, because a document that contradicts the code is
how a later session "fixes" the code.

---

## 7. Two sweeps, because hand-written coverage of a set covers what existed

Abuse case 1 had three per-route permission classes. Abuse case 9 had four
listed URLs, against a spec sentence that says *swept rather than
spot-checked*. Both now enumerate the URL conf.

The path sweep drives every requestable route anonymously **and as a signed-in
administrator** — a serializer rendering a reversed admin URL would do it for
the person who has one — plus a 404 and a 403. The 404 is the case worth
naming: Django's *debug* 404 lists every URL pattern it tried, admin included.
`DEBUG` is False here and in production, and there is now a test that says so
instead of an assumption.

Each sweep has a twin asserting it visited something, and the path sweep has a
second twin asserting the needle would be found if present. A sweep over an
empty enumeration passes forever and reads as thorough.

---

## 8. Three false claims, all mine, all caught by trying them

ADR-009 exists because M3 shipped three confidently wrong performance
docstrings. M10 produced three more, and the pattern is stable enough to be
worth naming: **the plausible sentence about why code is fast is the one to
distrust.**

- *"`select_related("actor")` would move the query count."* It does not. A join
  changes one query's shape, not the number of them; every test passed with it
  added. The real argument against it is that it buys a column the row already
  carries and carries nothing for rows whose actor is gone. What the flatness
  test *does* catch was then proven: rendering `actor.email` fans out to 10
  queries for one row and 19 for ten.
- *"`actor` and `request` are unused in `issue_refund`."* `actor` is read.
- *"Looking the object up after validation is what stops id probing."* The
  permission class does that. The ordering is now pinned by a test rather than
  asserted in a comment.

Two tests also failed with a crash rather than an assertion before being
fixed — an `IndexError` from splitting a printed list, a `TypeError` from
building `"/" + None`. **A test whose failure mode is a crash says less than
one that fails on its claim**, because the crash does not tell you which claim
was wrong.

---

## 9. The suite's runtime was misdiagnosed, and the number is recorded here

It was reported in-session that a full run took about an hour and that Argon2
was the cause. Measured afterwards:

| Configuration | Full suite |
|---|---|
| MD5 hashers, MinIO up | **82s**, reproducible |
| Argon2 hashers, MinIO up | **248s** |
| MD5 hashers, MinIO down | 963s, once, never reproduced |

The test-only MD5 hasher is worth a real **3x** and stands on that. The hour
was the first run stalling on pytest-django's *delete the existing test
database?* prompt with no stdin, which reads as slow progress rather than a
block. Object storage costs 31.6s in a single file when nothing answers,
because each skip waits out a connection timeout first — **run the suite with
MinIO up.**

Nothing was given up for the speed: the assertions that production uses Argon2,
keeps PBKDF2 beneath it, and produces an `argon2$` hash now read *production*
settings in a clean interpreter, and were provoked against a PBKDF2-first
`base.py`. What is genuinely reduced is that no test exercises Argon2
in-process, so Django's upgrade-on-next-login path runs on MD5 in tests.

---

## 10. Carried out of M10

- **`AccessOverride.granted_by` is `PROTECT`.** ADR-018 §5 argued at length
  that `AuditLog.actor` must be `SET_NULL` so an audit row never becomes the
  reason an account cannot be deleted. It does not — but M4's override table
  does: an administrator who has ever granted an override cannot be deleted at
  all, and the audit row's `SET_NULL` never gets the chance to matter. Found by
  an abuse case 7 test failing with `ProtectedError`. **A real gap against
  erasure obligations**, belonging with the user-deletion work spec §6 already
  places outside M10.
- **`admin_trail_for` and the refund route**, both above, both owned by M8.
- **No IP allow-list**, ADR-018 §2 — M13, when the hosting target is known.
- **`client_ip` records the proxy, not the administrator.** `audit.py` says so
  plainly; fixing it means knowing the trusted proxy depth, which is a
  deployment fact. M13.
