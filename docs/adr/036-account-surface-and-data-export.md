# ADR-036 — An account surface, a data export, and why erasure is not here

**Status:** accepted — implemented 2026-09-29. **§5 is a decision for the owner and
is not made by this ADR.**
**Date:** 2026-09-29
**Decides:** what a person can see and do about their own account and their own data,
and which parts of that are not engineering questions
**Depends on:** CLAUDE.md invariants 2, 3, 9 and 10; §6 (do not invent facts about the
product); ADR-004 (echo the API's wording); `docs/specs/m10-admin.md` §6, which
deferred both export and erasure

---

## Decision

**An account page** at `/account`, showing what `/auth/me/` returns and nothing
derived from it, plus a working password change.

**A synchronous data export** at `GET /auth/me/export/`, as a JSON download.

**No account deletion**, and no stub for one. §5 says what it would need.

**`AccessSerializer` carries the reason's `label`**, so no client keeps its own copy
of a twelve-string vocabulary.

---

## 1. What was missing, and how much of it was already built

Nothing existed at `/account`. More usefully: **`POST /auth/password/change/` had no
caller** — the only authenticated endpoint in the auth group, present since M2. A
signed-in learner could change their password only by signing out and using the
emailed reset, which needs their inbox.

That is the fourth endpoint this addendum has found with no caller, after
`verify-email`, `resend-verification` and the reset confirmation (ADR-034 §1). The
pattern is worth naming: **a wrapper in `client.ts` looks like coverage and proves
only that somebody typed the URL.** `docs/specs/frontend-state-and-api.md` §7 now
carries the grep that finds them, along with the reason the naive version of that grep
misreports a chained call.

---

## 2. Why the access label moved to the server

`resolve_account_access` can return **twelve of the fourteen reasons** — every one
except the two lesson-specific grants — and an account page needs words for all
twelve.

The frontend alternative is a `Record<Reason, string>` of its own. That is a second
copy of this vocabulary, and `denial.ts` already documents what such a copy costs:
`LessonPlayer` branched for nine milestones on `SUBSCRIPTION_PAST_DUE` and
`NOT_AUTHENTICATED`, **neither of which has ever been a `Reason`** — two dead branches
and four real refusals with none.

So `AccessSerializer` gained `label`, rendered from `Reason(...).label`, and the page
displays it. Three properties follow:

- `reason` remains the thing to branch on. ADR-004's rule is unchanged: a client
  branches on the type and **echoes** the wording.
- A reason added in M8 or M9 arrives with words already attached.
- The values stay the stable contract; a label is presentation and may be reworded
  without that being a breaking change. The enum's own docstring is explicit that
  renaming a *value* is an API change — this is deliberately not that.

The frontend adds exactly one thing: where each of the three CTAs leads, as a
`Record` over the generated union, so an M8 addition is a compile error rather than a
missing button.

**`update_payment` points at `/pricing`**, which says plainly that pricing is not
announced. There is no provider and no card to update (§11 #1), so this is the honest
placeholder — pinned by a test, so M8 has to change it deliberately rather than
discover it.

---

## 3. The export: what is in it, and what is deliberately not

`GET /auth/me/export/`, JSON, as a download. GDPR Article 15 (access) and Article 20
(portability).

**In:** the account row, the profile's display name, courses started with their slugs
and titles, per-lesson progress with the three position figures, and subscriptions
**with their history** — `SubscriptionEvent` exists because "a mutable status answers
*what is true now*; it cannot answer *why is this person's access wrong*", and the
second question is what people export their data to answer.

| Out | Why |
|---|---|
| **`AuditLog`** | Every row carries an `actor_label` naming **another person** — the administrator who acted. Article 15 covers the requester's own data and does not extend to other people's, so handing over a log of who touched an account would disclose staff identities to anyone who asked. If a regulator ever requires it, the answer is a redacted projection, not this table |
| **`AccessOverride.granted_by`** | The same principle in miniature. The grant, its reason and its window are the person's own data; the name of the administrator who granted it is somebody else's. **The row is included and that one field is not** |
| Password material, token hashes | A credential is not data about somebody in any useful sense. A hash discloses nothing and is the one thing here that must never leave the database |
| **`WebhookEvent`** | Not keyed to a user at all — provider payloads with signatures and delivery metadata — so "this person's webhooks" is not a question this schema can answer. It becomes a real one at M8, and saying so is better than implying the export is complete |
| Course content, transcripts | The product, not personal data. Only the slugs and titles needed to make a progress row legible: `lesson: 9f3c…` is technically complete and useless to the person who asked |

**Synchronous, and the threshold is stated rather than assumed.** A curated catalogue
means tens of courses, one enrolment per course and one progress row per lesson
watched, and the query count is **eight regardless** — counted, pinned by a test. An
asynchronous job writing to R2 and emailing an expiring link is the right shape at the
point where a single response would time out. This is nowhere near it, and building it
now would add a Celery task, a storage object and a signed URL to serve something that
fits in a response body.

**A GET, so `Cache-Control: no-store`.** An export sitting in a shared proxy or a disk
cache is somebody's whole profile left on a machine they borrowed. The filename
carries the account id rather than the address, because an export gets saved and
forwarded and an email address in a filename is an email address in every directory
listing that touches it afterwards.

---

## 4. A guard changed the design, and it was right to

The first version imported `Subscription` into `apps/accounts/selectors.py`.
`TestNothingElseRederivesAccess` refused it: **nothing outside `apps/entitlements/`
may import the subscription model or its status enum**, because that import is the
seam where a second entitlement rule appears.

Nothing in the export decides access — the status is read as a value to print, never
compared — so the refusal was, strictly, a false positive.

**The exemption was still the wrong fix.** CLAUDE.md §6 forbids weakening a control
to make a test pass, and the guard's suspicion is sound: the next person to add
something to this export will be one line away from `if subscription.status ==`. The
subscription reads moved into `entitlements.selectors.personal_billing_data`, which
returns plain dictionaries so the caller cannot read anything off a model that the
function did not choose to disclose. Better layering, arrived at by being told no.

---

## 5. Erasure — **not built, and this is the decision the owner owns**

`docs/specs/m10-admin.md` §6: *"No user deletion or data-export flow. Erasure
obligations are real and are their own piece of work."* The admin refuses deletion
outright, and two model comments already describe the intended shape: *"anonymise the
person, keep the content"* and *"GDPR erasure anonymises the person while keeping the
history"*.

The engineering is not the hard part. **What must survive an erasure is, and every
answer has legal weight:**

| Question | Why it is not ours to answer |
|---|---|
| **Invoices and subscription history** | Tax law in the operating jurisdiction typically requires retention for years, and that jurisdiction is itself unresolved (§11 #1). Erasing a payment record to honour Article 17 may breach a retention duty |
| **The audit trail** | ADR-018's whole argument is that the audit log's only job is to be complete. `actor_label` is denormalised precisely so a row survives its actor's deletion — the schema is ready for anonymisation, and *what* to anonymise is a policy choice |
| **Instructor-authored content** | A course an instructor wrote outlives their account. `catalog/models.py` already says "anonymise the person, keep the content", which is a decision about attribution nobody has ratified |
| **Where a request arrives** | There is no contact route. No support address exists anywhere in this repository, so today there is no way to ask |

Until those are answered, the account page **says the gap out loud and names no
channel**. A published address nobody reads is worse than an admitted gap, and a
delete button in front of an unanswered retention question is worse than both.

---

## 6. Two invented facts, caught before they shipped

Worth recording as a pair, because they are the same mistake in two places and §6
names exactly this class.

1. The account page's first draft said **"email support"**. There is no support
   address anywhere in this repository.
2. The export's own `about` text said **"See the privacy documentation"**. There is no
   privacy documentation — that page is blocked on owner-supplied content (ADR-035 §5).

Both were plausible, both read as helpful, and both would have sent somebody
exercising a data right into a void. Both now state what is true and point at nothing,
and **both have tests pinning the absence** — `DataExport.test.tsx` asserts no address
appears in the component at all, and the backend asserts `about` contains no pointer.

---

## Consequences

**Positive.** A person can see what the product knows about them, change their
password without leaving, and take their data with them. One more endpoint gained its
first caller. The entitlement vocabulary now lives in one place.

**Negative.** The account page is honest about being incomplete, which is a worse
experience than a complete one — somebody looking for "delete my account" finds a
sentence instead of a control. That is the correct trade while §5 is open, not a
permanent state.

**Security.** The export is the highest-value read in the product, and it takes no
identifier at all: identity comes from the session, so there is nothing to
manipulate — architecture.md §4.4's "most common IDOR in DRF codebases" is
unreachable here by construction. `no-store`, a low throttle (`6/hour`), and the
filename carrying an id rather than an address. Nothing auth-related touches storage
(invariant 9).

**Performance.** Eight queries, fixed. The `prefetch_related` on subscription events
and `select_related` on progress rows are both load-bearing and both pinned.

**Accessibility.** The new page is in `verify:a11y`'s sweep — 13 built pages now — and
axe runs over the account details, the password form with a field error showing, and
the export section. The password fields declare `current-password` and `new-password`,
which is WCAG 2.2 AA 3.3.8 on a form that sits outside `(auth)` and so outside the
existing guard for it; a test asserts both values and their order.

---

## Verification criteria

1. **Done.** 30 provocations across the two changes — 16 for the account page, 14 for
   the export — each confirmed to fail the test that protects it.
2. **One test could not fail, and provoking found it.** "States whether access is
   allowed, from `allowed` and not from the reason" used fixtures where both readings
   agree, so replacing the read with the derivation left it green. `GRACE_PERIOD` and
   `TRIAL` are grants; keying on `SUBSCRIPTION_ACTIVE` denies a paying customer
   mid-grace and every trial user. Fixed and re-provoked.
3. **Done.** Backend 1557 tests, frontend 553. `ruff check`, `ruff format`,
   `manage.py check --deploy`, `tsc`, `eslint` and all three `verify:*` clean. Schema
   and frontend types regenerated.
4. **Done, and this is the first thing in the addendum verified against the live API
   rather than recorded responses.** A real session through the Next rewrite: the
   export returned 200 with `Content-Disposition: attachment`,
   `Cache-Control: no-store`, all seven sections present, and no occurrence of
   `password`, `argon2` or `token_hash` in the file.
5. **Outstanding, needs a person:** the account page has never been walked with a
   keyboard or a screen reader. Runbook §3.2.
6. **Outstanding, needs the owner:** §5, in full.

## Related

ADR-004, ADR-018, ADR-034, ADR-035; `docs/specs/m10-admin.md` §6;
`docs/specs/frontend-state-and-api.md` §7; CLAUDE.md §11 #1.
