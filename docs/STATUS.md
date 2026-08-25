# STATUS

**Last updated:** 2026-08-25
**Updated by:** agent session (M11 complete)

---

## Current milestone

**M11 — Discovery & Notifications. Complete — 8 of 8.**
Branch: `feat/m11-discovery`, off `master` at `ad80d18` (M10 merged, PR #37).

Spec: `docs/specs/m11-discovery.md`
Decisions: `docs/adr/020-m11-discovery-decisions.md` (before code),
`docs/adr/021-m11-discovery-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + five decisions | **done** — `56e9649` |
| T2 `search_vector`, GIN, `pg_trgm`, backfill | **done** — `bf129fd` |
| T3 search endpoint, ranked and throttled | **done** — `e5f0fde` |
| T4 catalogue filters | **done** — `1e70311` |
| T5 related courses | **done** — `046c35d` |
| T6 email adapter + Celery task | **done** — `192b9ce` |
| T7 the transactional set, in templates | **done** — `edbda25` |
| T8 abuse cases, ADR-021, close-out | **done** — `e16df20` |

**1229 tests pass, none skipped**, in 88s — ruff, `tsc`, `eslint` and
`check --deploy` clean, schema and types regenerate to no diff. Run with
Postgres *and* MinIO up.

### M11 is backend-only, on the owner's decision

architecture.md:1050 lists an accessibility pass and mobile QA. There is no
frontend to apply them to — auth pages and one lesson page — so a green
accessibility report over three pages would be ADR-006's inert control wearing
a compliance badge. Dropped, and recorded rather than absorbed.

### Three bugs, each found by a test built so only the rule could pass it

- **Related courses ranked by nothing.** Overlap was counted with a single
  `Case` holding one `When` per skill area, and `Case` returns the *first*
  match — so sharing five areas scored the same as sharing one.
- **Search had an unauthenticated 500.** `?q=%00` reached the driver;
  PostgreSQL text cannot hold a NUL byte. One request, no account.
- **A notification broke the action it described.** Abuse case 7's first
  version *raised* on an unverified address, so an unverified learner changing
  their password got a 500 from the notice about the change.

The first two were caught because the fixtures were built so nothing else could
produce the answer — the weaker related candidate is deliberately the more
recent one, and the abuse case listed control characters rather than only long
input. **That is M11's standing lesson:** a test whose fixture happens to order
correctly proves nothing.

### Two abuse cases are reworded rather than claimed

**Case 7** now names its two exemptions — verification and password reset exist
to reach an unconfirmed address — and says a withheld message is skipped and
logged, never raised.

**Case 8 is unmet by design.** Delivery is at-least-once; at-most-once needs
the table ADR-020 §8 declined or a provider idempotency key that does not exist
yet. `TestCaseEightIsNotMet` asserts the duplicate, because a missing test and
a satisfied one look identical in a summary.

### ADR-020 §7 was wrong and ADR-021 §1 says so

It called M2's direct `send_mail` an invariant-4 violation. The code it accused
had already argued the opposite in a docstring — Django's framework speaks SMTP,
and so does Resend — and that argument holds. What was actually wrong was the
synchronous send in the request path, and the five more call sites T7 was about
to add. **An ADR that accuses existing code should quote what that code says for
itself.**

### Fixed after close-out: the catalogue's missing instructor name

`PublicCourseSerializer.instructor_name` sourced `instructor.get_full_name`,
which `User` does not have — and `read_only` makes DRF `SkipField` rather than
error, so the field was **silently absent from every catalogue response since
M3** and no test asserted it.

**Fixed in `059cdbd`.** `InstructorProfile` gained `display_name` — it had
`headline` and `bio` and no name, while `StudentProfile` had one, and that
asymmetry is what the serializer was reaching around. The field is a method
field returning the name or `""`: present and empty beats silently absent.
Joined with `select_related` and pinned at two dataset sizes, because rendering
a name off a related row is the textbook N+1. Settable in Django Admin, because
a field nothing can write is always empty and an instructor profile API would
be an endpoint with no caller.

The tests assert the **key is present**, not only its value — every value
assertion would pass against a response missing the field, which is how this
survived eight milestones. ADR-021 §7 records the original finding.

### What is next

**M12 — Hardening.** Its Playwright objective is **unbuildable** until the
frontend-ownership question in ADR-020 §2 is answered; M7 raised it, M11 hit it
from the other side, and it belongs in CLAUDE.md §11 where an agent should not
put it unasked.

M8 and M9 remain blocked on the payment provider and the trial scoping rule,
and M8 still inherits M10's two follow-ups — moving the refund route into the
audited half of the route inventory, and teaching `admin_trail_for` about
subscription-targeted rows.

---

## M10 — Admin & Moderation. Complete — 10 of 10.
Branch: `feat/m10-admin`, which branches off `master` (M7 merged at `0e3124b`).

Spec: `docs/specs/m10-admin.md`
Decisions: `docs/adr/018-m10-admin-decisions.md` (before code),
`docs/adr/019-m10-admin-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + five decisions | **done** — `db46bf8` |
| T2 `AuditLog`, index, append-only | **done** — `79f80a8` |
| T3 `record_admin_action` + one-writer guard | **done** — `fef8fb9` |
| T4 access override write path, audited | **done** — `a57546e` |
| T5 route the Django admin: obscure path, staff-only | **done** — `7b0e654` |
| T6 2FA: `django-otp` enrolment and enforcement | **done** — `e51b096` |
| T7 audit the existing admin actions | **done** — `ac01da3` |
| T8 refund service and audit, no provider call | **done** — `3a5cfd6` |
| T9 audit log read surface + diagnostics extension | **done** — `0717a7b` |
| T10 abuse cases, schema, types, ADR-019, close-out | **done** — `c644502` |

**1114 tests pass, none skipped**, in 81s — ruff check and format clean,
frontend `tsc` and `eslint` clean, `check --deploy` reports no issues and 0
silenced, and the committed OpenAPI document regenerates to no diff. Run with
Postgres *and* MinIO up, so the object-storage tests run rather than skipping.
Nothing in the suite is unrun.

### What is next

**M11 — Discovery & notifications.** M8 and M9 sit earlier in §10's order and
are both still blocked: M8 on the payment provider and jurisdiction (§11 #1),
and additionally owes the webhook signature timestamp (ADR-013 §6) and the
`billing:` idempotency namespace (ADR-015 §5); M9 on the trial scoping rule
(ADR-010 §2), which must be answered before any self-serve trial ships.

M8 also inherits two things from M10 that will be wrong if it forgets them: the
refund route must move from `NOT_YET_CAPABLE` into `AUDITED` in the route
inventory, and `admin_trail_for` must learn about subscription-targeted rows or
the first real refund will be missing from diagnostics. The first fails a test
until it is done; the second does not, which is why it is written here.

### All ten abuse cases have a test, and two were weaker than the spec asked

T10 audited §4 case by case. Eight were genuinely covered. Two were not:

- **Case 1** had three hand-written per-route permission classes. It now sweeps
  every route under `/admin-api/` from the URL conf, as anonymous, student,
  instructor and `is_staff`-without-the-role.
- **Case 9** says the admin path must be absent "swept rather than
  spot-checked", and was four hand-listed URLs. It now sweeps every requestable
  route anonymously *and* as a signed-in administrator, plus a 404 and a 403.
  The 404 is the one worth naming: Django's **debug** 404 lists every URL
  pattern it tried, admin included, so there is now a test asserting `DEBUG` is
  off rather than an assumption.

Both sweeps have twins asserting they visited something, and the path sweep has
a second twin asserting the needle would be found if present. Provoked: an
unguarded `/admin-api/` route fails three, a leaked path fails two, an unknown
URL converter fails the coverage twin.

**Case 1's second half is not met and is now recorded as such.** An ordinary
user who finds the admin path sees Django's login form, which identifies
itself. The controls that operate are the unguessable path, `is_staff` and
mandatory TOTP. Changing `HardenedAdminSite` to answer 404 is a defensible
follow-up and was declined as a behaviour change to a routed production surface
on a milestone's closing task. ADR-019 §5.

**Case 8's wording was the other correction.** It read as though diagnostics had
to drop `provider_subscription_id`, contradicting M4's deliberate inclusion of
it. Settled as being about what a *non-admin* learns; the spec is reworded so
the document and the code stop disagreeing. ADR-019 §6.

### ADR-019 §1 is the standing rule to carry forward

**A decision recorded in an ADR is not a control until something asserts it.**
ADR-018 §6 said `AuditLog` was registered read-only in the admin. It was never
registered at all, and abuse case 6 passed for seven tasks because there was no
surface to edit through. This is ADR-006's shape one level up: a control nobody
provoked may be inert, and a control nobody *wrote* still reads as done to
anyone holding the document that promised it.

### The suite's runtime, measured rather than guessed

Earlier in this session I wrote that a full run took about an hour and that
Argon2 was why. **Both halves of that were wrong**, and the correction is
worth keeping because a wrong performance diagnosis is how the wrong fix gets
approved.

| Configuration | Full suite |
|---|---|
| MD5 hashers, MinIO up | **82s** — reproducible |
| Argon2 hashers, MinIO up | **248s** |
| MD5 hashers, MinIO down | 963s, once, not reproduced |

So the hasher change (`50ced9d`) is worth a genuine **3x**, not the order of
magnitude claimed for it. The hour came from somewhere else: the first run had
no `--reuse-db` and stalled on pytest-django's "delete the existing test
database?" prompt with no stdin, which looked like slow progress rather than a
block. Object storage adds its own cost when nothing answers — measured at
31.6s for one file with nine skips, because each skip waits for a connection
to time out first. **Run the suite with MinIO up.**

The hasher change itself stands, on the 3x. **Nothing was given up** — the
three assertions that production uses Argon2, keeps PBKDF2 beneath it, and
really produces an `argon2$` hash read *production* settings in a clean
interpreter, and were provoked against a PBKDF2-first `base.py` to confirm
they still fail. What is genuinely reduced: no test exercises Argon2
in-process any more, so Django's upgrade-on-next-login path runs on MD5 in
tests.

### T9 found that ADR-018 §6 had never been kept

`AuditLog` was **not registered in the Django admin at all**. ADR-018 §6 said
it would be, "read-only, with add, change and delete permissions all denied",
and T2 shipped the model without it. Abuse case 6 — *an audit row cannot be
edited or deleted through any surface we ship* — had therefore been passing
because there was no surface, which is a different fact from the one it
asserts. T9 registers it and tests the refusals, including the bulk delete
action, which `has_delete_permission` alone does not remove.

### Two decisions settled for T9, on 2026-08-25

**Abuse case 8 versus M4's serializer.** §4 case 8 says diagnostics leaks "no
provider identifiers", and `SubscriptionDiagnosticSerializer` has carried
`provider_subscription_id` since M4 on purpose — it is the handle support needs
to find the same subscription in the provider's dashboard, on an
administrators-only endpoint. **Settled: the sentence means a non-admin learns
nothing; the field stays.** T10 should reword the spec rather than leave the
document and the code disagreeing.

**The trail is user-targeted rows only.** Overrides and role changes record the
user as their target. A course approval records the course, and a refund will
record the *subscription* — so **M8 must revisit `admin_trail_for`**, or the
first refund will be missing from the exact screen support opens to ask about
it. Joining through every object a user owns was declined now because T8 makes
a refund impossible and the join would be a path no test could reach.

Capped at 50, with the true total returned beside the rows: a list capped at
fifty that reported fifty would tell support they had seen everything. The
`metadata` blob is deliberately not rendered by the API — it is open-ended, and
an endpoint returning it wholesale would publish whatever a future
`record_admin_action(..., something=...)` put there. The whole row is readable
in the admin site, which is the surface for detail.

### Carried forward from T9 — an erasure gap that is not T9's to fix

**`AccessOverride.granted_by` is `PROTECT`.** ADR-018 §5 argued at length that
`AuditLog.actor` must be `SET_NULL` so that an audit row never becomes the
reason an account cannot be deleted. It does not — but M4's override table does:
an administrator who has ever granted an override cannot be deleted at all, and
the audit row's `SET_NULL` never gets the chance to matter. Found by an abuse
case 7 test failing with `ProtectedError`; the test now uses a role change and
says why. **This is a real gap against erasure obligations** and belongs with
the user-deletion work §6 already puts outside M10.

### Why this file was four days stale

The seven commits above did not update it, so the document that exists to
answer *where are we* said M7 while M10 was most of the way built. §10 requires
updating it at the end of every session. That is the whole of the failure and
the whole of the fix.

### T8's one open question was settled before T8 started

§2.2 puts four things in scope for the refund — permission check, service, audit
row, refusal cases. **The audit row is the one that cannot honestly be
written:** a refund that raises `RefundNotAvailable` did not happen, and a row
describing an action that did not happen is a false record. The suite already
guards against exactly that shape in `test_a_refused_approval_writes_nothing`.

Settled 2026-08-25: `REFUND_ISSUED` stays in the closed vocabulary as the
marker, and T8's audit obligation is met by the twin test asserting a refused
refund writes nothing. The alternative — a `refund()` seam on the provider
protocol, proven against a stub — was declined because it invents the provider
capability ADR-018 §3 forbids by name: partial refunds, currency, windows,
idempotency keys.

Two smaller calls settled with it. The refusal answers **501**, not 503, because
503 says *try again shortly* and 501 says *this server does not do this*. And
the request carries **no amount**, because `Subscription` deliberately holds no
money (`entitlements/providers/base.py` says so) and whether partial refunds
exist is a provider fact we do not have.

---

## M7 — Learning Experience. Complete — 10 of 10.

Branch: `feat/m7-learning`, which branches off `feat/m6-transcription`.

Spec: `docs/specs/m7-learning.md`
Decisions: `docs/adr/016-m7-learning-decisions.md` (before code),
`docs/adr/017-m7-learning-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `bd8e314` |
| T2 `Enrollment`, `LessonProgress` + constraints | **done** — `8d9b0ca` |
| T3 progress recording, completion defined once | **done** — `1b799ba` |
| T4 progress endpoint, gated and throttled | **done** — `0e3c8bf` |
| T5 resume: "my courses", last and next lesson | **done** — `ca8a39a` |
| T6 course completion rule | **done** — `98936bf` |
| T7 transcript panel, APPROVED only | **done** — `6c1a2b4` |
| T8 lesson page: player, panel, heartbeat | **done** — `620f45f` |
| T9 abuse cases, query counts | **done** — `1790788` |
| T10 schema, types, ADR-017, close-out | **done** |

**947 tests pass**, ruff clean, tsc/eslint/`next build` clean, `check --deploy`
clean. Schema and types regenerate to no diff. The entitlement resolver still
holds **100% branch coverage** — 94 statements, 32 branches, none missed.

### The milestone's claim was demonstrated, not asserted

ADR-016 §4 committed to one lesson page so that *watch → progress persists →
resume across devices* was something somebody had watched work. It was: played
against the live stack, left the page, came back at the right second, and the
lesson completed itself by watched time with the database agreeing.

That is also what found the two defects below. Neither was reachable from a
test.

### Two defects found by running it

**1. Every unsafe request through the proxy was refused.** `CSRF_TRUSTED_ORIGINS`
was never set. Next forwards its rewrite destination as the `Host` header, so
Django's origin is `api` and the browser's is `localhost:3000` — they can never
match. This broke **login too**, not just the new endpoints, and would have hit
production identically. Fixed in `07cdfac`. **M13 must set the variable** to the
public origin. ADR-017 §8.

**2. The player wrote a playhead of zero over a real bookmark.** The ticker's
cleanup reports a final beat, and React Strict Mode runs that cleanup before the
fetch saying where the learner was has returned. A lesson resumed at 0:00 having
just destroyed the thing the milestone exists to prove. Fixed with a readiness
gate. ADR-017 §6.

### Two comments that were confidently wrong

The transcript prefetch does **not** prevent a query per cue — a reverse foreign
key collection is one query however many rows it holds, and removing the
prefetch leaves the test passing. Corrected in `1790788`. This is the same shape
as M3's deferrable-constraint comment: right code, wrong reason, and no passing
test can see the difference. ADR-017 §7.

### Carried forward from M7

- **A completed course is not re-evaluated if a lesson is deleted**, so a
  learner one lesson short stays incomplete. No deletion flow exists yet —
  **M10**, where it first can.
- **"My courses" cannot be ordered by last activity**, because a cursor cannot
  page on an aggregate. Fine under twenty courses; needs a real column and a
  measurement if that changes. ADR-017 §3.
- **No frontend test runner.** Adding one is a §5 dependency decision, still
  unasked. Frontend verification is `tsc`, `eslint`, `next build`, and running
  it.
- **The frontend is auth pages plus one lesson page.** No catalogue, course or
  account surfaces exist. M12 asks for Playwright journeys over a UI that is
  mostly not built; that work is currently unowned by any milestone.

---

## M6 — Transcription & Subtitles. Complete — 10 of 10.

Branch: `feat/m6-transcription`.

Spec: `docs/specs/m6-transcription.md`
Decisions: `docs/adr/014-m6-transcription-decisions.md` (before code),
`docs/adr/015-m6-transcription-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `a5d7163` |
| T2 `Transcript`, `TranscriptSegment` + constraints | **done** — `fc8e099` |
| T3 transcription provider interface + fake | **done** — `79fb3d8` |
| T4 request transcription when media is ready | **done** — `e265bd4` |
| T5 callback receiver, segments written | **done** — `75740a6` |
| T6 segment editing, scoped | **done** — `c52649b` |
| T7 review workflow | **done** — `3283fde` |
| T8 VTT rendering, cached, gated | **done** — `7f28ec1` |
| T9 the serving gate, both halves proven | **done** — `98a4add` |
| T10 abuse cases, ADRs | **done** |

**819 tests pass**, ruff clean, tsc clean, `check --deploy` clean. The
entitlement resolver still holds 100% branch coverage.

### The one requirement met somewhere other than where the document put it

§10 M6 asks for a publish gate. ADR-014 §3 put the control at the point of
**serving** instead: the VTT endpoint returns only `APPROVED` transcripts.
That is stricter where it counts — it covers a lesson added to an
already-published course, which a publication-time gate never evaluates — and
looser where it does not, since a course whose subtitles are still being typed
can go live and teach.

Both halves are proven rather than assumed: publication is genuinely ungated
(including structurally — catalog's publication service does not know
transcripts exist), and a sweep across every learner-readable endpoint shows
unapproved words reaching nobody, run as a subscriber, anonymously, and with
the lesson marked a free preview.

**The risk ADR-014 §3 named itself** — that concentrating a requirement on one
reader means every later reader must remember it — is guarded structurally: no
app outside `transcripts` may import `Transcript` or `TranscriptSegment`, so a
future interactive transcript, search result or export has to come through the
app where the approved-only selector lives.

### Two bugs in earlier milestones, found by building this one

**M5's playback token was flaky one run in eight.** It joined raw HMAC bytes
with a `b"."` separator and split on the last one — but a digest byte can *be*
an ASCII dot. `pytest-randomly` made it look like a test-ordering problem.
Now base64-encoded per half, and guarded by 200 round trips rather than one,
because a single round trip passes seven times in eight.

**A shared idempotency table with unnamespaced providers.** Both fakes are
called `fake`, and `WebhookEvent` is unique on `(provider, provider_event_id)`
— so one id collision would discard a transcription callback as a duplicate
media event, answering 200 while the lesson silently never got subtitles.
Events are now `video:fake` and `transcription:fake`. **M8 must use
`billing:`** (ADR-015 §5).

### What the review step actually buys, stated plainly

It prevents approving a transcript **nobody has opened**. It does not prevent
approving one nobody has *read*. The stronger guarantee is per-segment
sign-off, which is a product decision rather than a correctness one — recorded
in ADR-015 §2 so the workflow is not read as more than it is.

---

## M5 — Media Pipeline. Complete — 10 of 10.

Branch: `feat/m5-media-pipeline`.

Spec: `docs/specs/m5-media-pipeline.md`
Decisions: `docs/adr/012-m5-media-decisions.md` (before code),
`docs/adr/013-m5-media-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `5aea854` |
| T2 `MediaAsset`, `WebhookEvent` + constraints | **done** |
| T3 storage adapter + MinIO | **done** |
| T4 presigned upload and completion | **done** — `fe82068` |
| T5 video provider interface + fake | **done** — `9879cf9` |
| T6 processing task, retries, DLQ | **done** — `8b7cd93` |
| T7 webhook receiver | **done** — `d782847` |
| T8 playback token behind the resolver | **done** — `edd5891` |
| T9 processing status + retry path | **done** — `cc81496` |
| T10 abuse cases, query counts, ADRs | **done** |

**653 tests pass**, ruff clean, tsc clean, `check --deploy` clean. The
entitlement resolver still holds 100% branch coverage.

### M5 costs nothing, and that was the point

Real S3 code against MinIO, a fake video provider behind the documented
interface (ADR-012 §1). The storage path is genuinely exercised — MinIO
refuses a substituted content type with a 403 — so what ships is the code that
will run in production with different environment variables.

**The Mux integration is unproven.** What is proven is that everything around
it is correct and the swap is one file. Same trade M4 made with billing.

### The bug that would have emptied the dead-letter queue

`complete_upload` was wrapped in `transaction.atomic`, so the failure path
wrote FAILED and then raised — and the raise rolled the record back. Every
rejected upload would have stayed PENDING with no message, and the queue §10
M5 calls *the* deliverable would have been permanently empty while appearing
to work.

### The test that only works because it asserts a side effect

Abuse case 6 asserts the provider adapter was **never called** on an
entitlement denial, not that the response lacked a token. Provoked by swapping
the order to mint first: three tests failed **and the endpoint still answered
403**. A test asserting only the status code would have passed while valid,
signed, working tokens were minted for people who may not watch.

### Two testing facts worth carrying forward

Celery's eager mode runs retries **inline**, so a test watching for a `Retry`
reports "did not raise" against code that retries correctly. And
`transaction.on_commit` **never fires under pytest-django** — the same
invisibility as ADR-009 §5's deferred constraints, in a new disguise.

### Carried into M8, unresolved

**The webhook signature has no timestamp.** Our scheme accepts a valid old
signature indefinitely. The idempotency table stops a duplicate being
*processed* twice but does not stop a captured payload being replayed months
later. Real providers bound this with a timestamp, and M8's adapter must add
it (ADR-013 §6).

---

## M4 — Entitlements. Complete — 10 of 10.

Branch: `feat/m4-entitlements`.

Spec: `docs/specs/m4-entitlements.md`
Decisions: `docs/adr/010-m4-entitlement-decisions.md`,
`docs/adr/011-a-field-gains-meaning-re-audit-who-writes-it.md` (standing rule)

| Task | State |
|---|---|
| T1 spec + four decisions put to the owner | **done** — `b0d3b20` |
| T2 `Subscription`, `SubscriptionEvent`, `AccessOverride` | **done** — `a7147fc` |
| T3 fake billing provider behind an adapter | **done** — `8102fc0` |
| T4 `resolve_access`, 100% branch | **done** — `f7f9755` |
| T5 Problem Details denial + permission class | **done** — `f841d5f` |
| T6 gated lesson endpoint | **done** — `bc8f8c9` |
| T7 `/auth/me/` carries the decision | **done** — `a11c740` |
| T8 admin diagnostics + override grant surface | **done** — `9a4b009` |
| T9 remaining abuse cases; `is_preview` fix | **done** — `9db0899` |
| T10 ADRs, schema, types | **done** |

**489 tests pass**, ruff clean, tsc clean, `check --deploy` clean. Schema and
types regenerate to no diff.

### The resolver has 100% branch coverage, enforced

CI fails the build if `apps.entitlements.resolver` drops below it. The gate was
provoked before being trusted — run against one test class it reports 46% and
errors — because a gate nobody has seen fail is ADR-006's inert control wearing
a new hat.

### All ten abuse cases have a test, and two found real bugs

**Abuse case 8 was live.** `is_preview` was writable on the instructor lesson
API from M3 T5. Nothing read the field then, so nothing looked wrong. M4 made
it the resolver's *first branch* — allowed before the caller is identified — so
an instructor could mark every lesson a preview and hand a whole course to the
internet, against a subscription shared across the catalogue. **ADR-011** is
the standing rule that came out of it: when a field starts being read by an
access decision, re-audit every path that can write it, in the same change.

**A complete bypass was introduced and caught inside T6.** The gated lesson
view was a `ReadOnlyModelViewSet`, which provides `list` as well as `retrieve`.
Object-level permissions are never consulted for a list, so `GET /lessons/`
answered 200 with every lesson body to anonymous callers, behind a docstring
that said "retrieve only". Object-level permissions cannot gate a collection —
that is now written down in ADR-010 §9.

### Abuse case 10 is the suite's only structural test

It parses every module outside `entitlements/` and fails if one imports the
subscription status enum or compares a status literal. A second implementation
of the access rules is invisible to behavioural tests; it shows up as a
disagreement in production, later. The detector is itself checked against the
pattern it exists to find.

### Two guards fired on schedule

M2's `test_the_access_object_is_absent_until_m4` was written to fail exactly
once, so nobody shipped a placeholder the frontend could depend on. It fired.
That is three milestone-order guards that have now gone off correctly across
M0–M4.

### Open, and blocking M9

**The trial scoping rule (spec §3.2) is undecided.** A trial was settled to be
*scoped* rather than equal to a paid subscription, but not what scopes it.
`trial_covers` currently grants what an active subscription grants, isolated in
one function.

That is safe today for one reason only: **there is no self-serve trial** — a
subscription can only be started by the `billing` management command. **M9 must
not ship a self-serve trial before this is answered**, or the permissive
default becomes a way to get the catalogue free. ADR-010 §2.

---

## M3 — Catalogue domain. Complete — 10 of 10.

Branch: `feat/m3-catalogue`.

Spec: `docs/specs/m3-catalogue.md`
Decisions: `docs/adr/007-m3-catalogue-decisions.md` (spec time),
`docs/adr/008-m3-implementation-decisions.md` (implementation),
`docs/adr/009-measure-do-not-reason-about-queries.md` (standing rule)

| Task | State |
|---|---|
| T1 spec + ADR-007 | **done** |
| T2 `Language`, `Course`, state machine | **done** |
| T3 `Section`, `Lesson`, deferrable ordering constraints | **done** |
| T4 instructor course API, scoped | **done** — `64ffbe6` |
| T5 section/lesson CRUD + bulk reorder | **done** — `aaa598f` |
| T6 submissions on the review trail | **done** — `ba4cac8` |
| T7 admin review queue, unrouted | **done** — `0c31bee` |
| T8 public catalogue | **done** — `15d8640` |
| T9 query counts pinned | **done** — `fef7617` |
| T10 ADRs, schema, types | **done** |

**352 tests pass**, ruff clean, tsc clean, `check --deploy` clean. Schema and
types regenerate to no diff.

### All nine abuse cases have a test that fails without its control

Including the two that are easy to fake. Abuse case 7 (reorder with a foreign
id) was checked against a deliberately permissive implementation — filter the
foreign id out, apply the rest — and both reorder tests failed against it.
Abuse cases 5 and 6 each have a **positive twin**: a filter matching *nothing*
would satisfy "the public never sees a draft" perfectly and ship an empty
catalogue, so one test archives a live course and watches it disappear.

### A fourth inert control, same shape as M2's two

`InstructorReviewEventViewSet` was declared
`(_CourseScopedViewSet, ReadOnlyModelViewSet)`. The scoped base already
extended `ModelViewSet`, so its `CreateModelMixin` won the MRO: **the route
accepted POSTs while its class name said it could not**, and an instructor
could have written themselves an `APPROVED` event. Caught only by a test that
provokes each verb individually. The shared base is now a mixin carrying no
verbs, so a viewset's own base decides what it accepts.

ADR-006 has now paid for itself four times. Read it before M4.

### Three false performance claims — ADR-009 is the response

I wrote three docstrings in this milestone that were confidently wrong: that
the reorder needed the deferrable constraint to survive `bulk_update` (it
survives by batching), that the catalogue list costs two queries (one — cursor
pagination issues no `COUNT`), and that two `select_related` calls saved a
query per row (they saved none; the serializers render those relations as
primary keys). All three read as correct in review. None would have failed a
functional test.

**ADR-009** makes measurement mandatory for any claim about query counts,
index use, lock behaviour or constraint timing, and describes how to write a
query-count test that means something: run the endpoint at two dataset sizes
and assert the count is *identical*, with a distinct related object per row,
and verify the test fails when the join is removed.

### Two things M4 inherits directly

- **The public serializer has no `body` field at all** (ADR-008 §6), rather
  than a conditionally hidden one. When `resolve_access` exists, entitled
  playback is a *different serializer* chosen by the resolver — not a
  conditional field added to this one. That regression is the thing to watch.
- **Django Admin is built and unrouted** (ADR-008 §5). A staff account that is
  not `role == ADMIN` cannot publish — proven against a superuser — but can
  still edit course fields. Who gets `is_staff` is M10's question.

---

## M2 — Authentication & Accounts. Complete — 10 of 10.

Branch: `feat/m2-authentication`.

Spec: `docs/specs/m2-authentication.md`
Decisions: `docs/adr/005-m2-authentication-decisions.md`,
`docs/adr/006-security-controls-must-be-provoked.md`

| Task | State |
|---|---|
| T1 custom `User` + first migration | **done** — `da72ff4` |
| T2 Argon2, session settings, `django-axes` | **done** — `07ebd47` |
| T3 account creation service | **done** — `1243253` |
| T4 registration + email verification | **done** — `abb7938` |
| T5 login / logout / CSRF bootstrap | **done** — `f189a68` |
| T6 password reset + confirm + change | **done** — `fa7daed` |
| T7 `GET /auth/me/` | **done** — `5805353` |
| T8 throttle scopes provoked and tested | **done** — `74f42ed` |
| T9 frontend auth flows + design foundation | **done** — `245d226` |
| T10 ADR, schema and types | **done** |

**252 tests pass**, ruff clean, tsc clean, `check --deploy` clean.

### All eight abuse cases are covered

Every case in `docs/specs/m2-authentication.md` now has a passing test. The
enumeration one includes the variant that matters most: a second registration
for a taken address does **not** overwrite the existing password.

### Two controls were configured and inert — read ADR-006 before M4

The `django-axes` lockout (T5) and every per-endpoint rate limit (T8) were
correctly configured, read correctly in review, and did nothing. Neither was
caught by review, types, or any functional test — only by a test that tried to
trip the control and saw it fail to trip.

**ADR-006 makes provoking a control the standard**, and it exists because M4's
entitlement resolver and M8's webhook signature check would fail the same way,
far more expensively: an inert entitlement check gives the product away, an
inert signature check makes the webhook a free-subscription API.

### ADR-005 §2.1 validated end to end

No BFF layer. Verified through the running stack: `csrf` sets the cookie,
register returns 202, login returns 200 and sets `sessionid`, `/auth/me/`
returns the right user — all through the Next rewrite.

Also landed: `21bad4c` fixed the bootstrap gap — `make bootstrap` now writes
`backend/.env` as well as the root one, so `make migrate` and local
`manage.py` work without exporting variables by hand.

**204 tests pass**, ruff clean, tsc clean, `check --deploy` clean.

### Tests now need Postgres

M2 is the first milestone with models. CI runs Postgres as a service
(`b36bdbb`) — chosen over SQLite deliberately, because the schema depends on a
functional unique constraint now and JSONB and full-text search later, so a
SQLite pass would prove nothing about production.

**Local gotcha, cost an hour:** a native **PostgreSQL 18 Windows service** on
this machine binds `0.0.0.0:5432` and wins over Docker's mapping for IPv4
loopback. Auth succeeded *inside* the container and failed from the host with
the same credentials. The compose stack now uses **`POSTGRES_PORT=5433`** (set
in the root `.env`). Third collision of this kind, after port 3000 and the
home-directory lockfile.

### The threat model is the spec

`docs/specs/m2-authentication.md` lists eight abuse cases. Three are now
covered:

- **1 — enumeration.** A taken address is indistinguishable from a free one at
  registration, *and* a second attempt does not overwrite the existing
  password. The second half is the one that would have been account takeover.
- **3 — privilege escalation.** `role`, `is_staff`, `is_superuser` and
  `is_email_verified` in a request body reach nothing: the serializer declares
  two fields, so there is no path from the wire to them.
- **4 & 5 — token replay and expiry.** Verification tokens are stored hashed,
  single-use and expiring. Unknown, expired and already-used give one
  indistinguishable answer, so a failed guess yields no information.

**Not yet proven: abuse case 6** (lockout not bypassed by changing User-Agent),
which lands with T5, and **7 and 8**, which land with T7.

### Milestone-order guards have now fired, all correctly

- The M0 `make migrate` guard refused for the whole of M1 and now permits.
- The M0 test asserting the default user model was written to fail *exactly
  once*, as a reminder to come back. It did, and has been replaced.
- The M1 schema drift gate failed the moment endpoints existed — and exposed
  something larger than drift: drf-spectacular cannot infer request bodies from
  a plain `APIView`, so generated types would have been empty and invariant 16
  satisfied in name only. Views are annotated; types describe real operations.

---

## M1 — Backend Foundation. Complete — 8 of 8.

| Task | State |
|---|---|
| T1 core app + abstract base models | **done** — `fae22ac` |
| T2 DRF + drf-spectacular configuration | **done** — `616eede`, pins fixed in `9f630ec` |
| T3 Problem Details exception handler | **done** — `0b565bb`, problem types in `ca56c72` |
| T4 pagination classes | **done** — `0616c15` |
| T5 `/healthz` | **done** — `9050775` |
| T6 `request_id` middleware + JSON logging | **done** — `c5eb681` |
| T7 `/api/v1/schema/` + drift gate | **done** — `38eb242` |
| T8 frontend type generation (`make types`) | **done** — `38eb242` |

### A redirect loop found by verifying, not by testing

`/api/v1/schema/` through the Next.js rewrite bounced forever: Next 308'd it to
`/api/v1/schema`, Django's `APPEND_SLASH` 301'd it back. **Every endpoint in
architecture.md §6.2 ends in a trailing slash**, so this would have broken all
of them from M2 onwards.

Two causes, both fixed in `next.config.ts`:

- Next's default `trailingSlash: false` strips the slash before the rewrite
  runs. Now `trailingSlash: true`, aligning with Django rather than disabling
  canonical redirects on the static marketing surface (invariant 15).
- The rewrite used `:path*`, which splits on `/` and swallows the terminal
  slash. Now `:path(.*)`, a greedy capture that forwards the path verbatim.

Verified through the running stack: with slash, without slash, and the
marketing root all return 200. **No automated test covers this** — it needs
both services running, so it belongs in the Playwright journeys at M12. Worth
adding there explicitly.

### Known and unresolved

One plain-text duplicate line appears per Django log record in the container.
The logger tree was probed in place and is correct — root and `django` both on
`JsonFormatter`, `django.request` propagating with no handlers of its own — so
the source is elsewhere, most likely uvicorn's own logging config. **Cosmetic
log volume, not correctness:** the correlated JSON line is present and right.
Timeboxed after three diagnostic rounds per `CLAUDE.md` §9.

**ADR-003** settles that M1 creates no concrete models and no migrations; the
audit log moves to M2, after the custom `User`. A test drives the migration
autodetector directly and fails the build if anything under `apps/` grows a
model.

**ADR-004** settles that clients branch on the RFC 9457 `type` member rather
than the status code, because DRF downgrades `NotAuthenticated` to 403 when no
authenticator offers a `WWW-Authenticate` header — so "log in" and "not
allowed" share a status. The same mechanism carries M4's entitlement reasons:
`EntitlementDenied` will declare a `problem_type` and add `reason`/`cta`
without the handler changing.

88 tests pass, ruff clean, `check --deploy` clean, 100% branch coverage on the
exception handler.

### Three CI failures, all the same root cause

Both were environment drift — the local machine had state CI did not, and both
are now guarded:

- **DRF installed but not pinned** in `pyproject.toml`. Fixed in `9f630ec`.
  Standard now: verify dependency changes by installing into a *fresh*
  virtualenv from `pyproject.toml` alone, not with `--dry-run`.
- **The suite required a live Redis**, because T2 pointed `CACHES` at Redis and
  DRF throttling counts against the default cache. It passed locally only
  because the compose stack was running. Fixed in `6a6e600`: test settings use
  `LocMemCache`, and the production assertions moved to a subprocess check
  against production settings. Reproduce this class of failure by stopping the
  relevant compose service before trusting a green local run.
- **`REDIS_CACHE_URL` was never added to the CI workflow.** T2 added it as a
  required variable and taught `.env.example`, `test.py` and
  `docker-compose.yml` about it — but not `ci.yml`, so `check --deploy` died
  with `ImproperlyConfigured`. Fixed **and guarded** in `0e9b4fe`: a test parses
  `ci.yml`, extracts what the deployment step supplies, and compares it against
  every default-less `env()` read in `base.py`. **This class of drift is now
  caught by the suite** rather than by CI.

---

## M0 — Planning & Foundations. Complete and verified.

All 11 tasks implemented, all 11 verified by running them.

| Task | State |
|---|---|
| T1 repository skeleton | **done** — `1ebf740`, plus `.gitattributes` in `9d1cf0d` |
| T2 backend settings split | **done** — `c322d8d` |
| T3 ASGI runtime | **done** — `196668c` |
| T4 Celery application | **done** — `48bf163` |
| T5 backend Dockerfile | **done** — `b55505b` |
| T6 frontend scaffold | **done** — `66c314b` |
| T7 frontend Dockerfile | **done** — `ff13b77` |
| T8 docker-compose | **done** — `38ca0ae`, corrected in `883c225` |
| T9 `.env.example` | **done** — `fdcb9c3` |
| T10 CI workflow | **done** — `4982b92`, fixed in `36be0e9` |
| T11 Makefile | **done** — `e9cc85e` |

### The stack, verified

All six services start. `postgres`, `redis`, `api` and `mailpit` report
healthy; the worker connects to Redis and reports ready; the web root returns
200; and a request to `/api/` on the **web** origin is answered by Django with
`Server: uvicorn` — ADR-001 §2.1 same-origin routing proven rather than
assumed.

Two bugs surfaced only here, neither visible in isolation:

- **`local.py` hardcoded `ALLOWED_HOSTS`**, silently overriding the environment
  read in `base.py`. Next forwards the rewrite destination as the Host header,
  so Django saw `api:8000` and rejected every proxied request while
  `DJANGO_ALLOWED_HOSTS` in compose did nothing. Fixed in `883c225` with a
  regression test.
- **The mailpit pin was wrong** (`v1.27`), taken from `docker manifest inspect`
  output that had already proved unreliable. The real version is **v1.30.7**,
  confirmed by running the image and pulling that exact tag.

Host ports are overridable (`WEB_PORT`, `API_PORT`, `POSTGRES_PORT`,
`REDIS_PORT`, `MAILPIT_UI_PORT`, `MAILPIT_SMTP_PORT`); container ports are
fixed. Port 3000 on this machine is held by an unrelated project.

### Verified

Backend — 27 tests pass; `ruff check` and `ruff format --check` clean across
`backend/` and `scripts/`; `manage.py check` clean; `manage.py check --deploy`
reports **no issues, 0 silenced** against production settings.

Frontend — `tsc --noEmit` clean, `eslint` clean, production build succeeds with
no warnings.

CI — workflow YAML parses into the two intended jobs. **Not** verified that the
run passes on GitHub; only a push can show that.

### Invariants now enforced by tests, not convention

| Invariant | Guard |
|---|---|
| 5, 9 — sessions in Postgres | asserts `SESSION_ENGINE` is the DB backend |
| 12 — ASGI only | asserts `config/wsgi.py` does not exist |
| 5 — no local disk writes | asserts Gunicorn logs to stdout/stderr |
| ADR-001 §2.2 — Beat deferred | asserts no beat schedule and `django_celery_beat` uninstalled |
| §6 — no values in `.env.example` | parses every env read and asserts documented, name-only |
| M2 custom User ordering | `make migrate` refuses while `AUTH_USER_MODEL` is the default |

### Version matrix (locked to what is installed, not proposed)

Python 3.12.6 · Node 22.20.0 · Docker 29.1.3 / Compose v2.40.3 · PostgreSQL 16 (target)

Django 5.2.17 · django-environ 0.14.0 · psycopg 3.3.4 · gunicorn 26.0.0 ·
uvicorn 0.52.3 · uvicorn-worker 0.4.0 · celery 5.6.3 · redis 8.1.0 ·
ruff 0.16.3 · pytest 9.1.1 · pytest-django 4.14.0 · pytest-cov 7.1.0

Deliberately absent from M0: DRF, drf-spectacular, django-celery-beat,
django-axes, argon2-cffi, Vitest.

---

## The M0 planning session, kept as written

Everything below this line is the record of the first session, before any code
existed. It is left unedited as history — "Still no application code" and
"blocked on approval of the M0 plan" describe **2026 before M0**, not today.
The current state is at the top of this file.

The one part still live is the open-decisions table, which is why it has not
been folded away.

## Completed

- **Documentation reorganised** into `docs/` and untracked. `docs/` is gitignored; the files remain on disk. `CLAUDE.md` stays at the repository root because the agent tooling loads it from there.

  | Was | Now |
  |---|---|
  | `phase-1-architecture.md` | `docs/architecture.md` |
  | `deployment-strategy.md` | `docs/deployment-strategy.md` |
  | `adr-002-cost-reliability-streaming.md` | `docs/adr/002-cost-reliability-streaming.md` |
  | `agent-prompts.md` | `docs/prompts/agent-prompts.md` |

  This makes the paths in `CLAUDE.md` §2 correct for the first time. The removals are staged in git but **not committed**.

- **`.gitignore` created** — `docs/`, `.env`, `.env.*` with `!.env.example`. The full ignore file lands with M0 task T1.
- **`docs/adr/001-architecture.md` written** — records the four settled decisions (same-origin routing, Celery Beat placement, hosting deferral, ASGI) and restates the payment provider as open with a standing "do not model billing" instruction.
- **M0 plan produced** — 11 tasks, ordered, with dependencies and invariant mapping. Awaiting approval.

Still no application code, no dependencies, no migrations, no tests. `backend/`, `frontend/`, `infra/`, `scripts/`, `.github/` do not exist.

---

## In progress

None. Blocked on approval of the M0 plan and the version matrix (below).

---

## Blockers

### Blocking the first M0 task

1. **Version matrix not agreed.** `pyproject.toml` and `docker-compose.yml` cannot be pinned without Python, Django, Node, Next.js, PostgreSQL and Redis versions. Proposed defaults are in the M0 plan §8; they need confirming or correcting.
2. **Dependency approval.** `CLAUDE.md` §5 requires approval for every dependency. M0 needs roughly nine runtime and six dev packages. The list is in the M0 plan §8. Decide once whether `docs/architecture.md` counts as a standing allowlist, or this recurs every milestone.

### Open decisions (`CLAUDE.md` §11)

| # | Decision | State |
|---|---|---|
| 1 | Payment provider & jurisdiction | **Open.** Blocks M4 schema and M8. Does not block M0–M3. Standing rule: do not model billing. |
| 2 | Same-origin routing | **Settled** — ADR-001 §2.1. Next.js rewrites now, Cloudflare Worker before launch. |
| 3 | Celery Beat placement | **Settled** — ADR-001 §2.2. In-worker, single replica. `--beat` and `django-celery-beat` land with the first periodic task, not in M0. |
| 4 | Hosting target | **Settled as deferred** — ADR-001 §2.3. Containerise for both; decide at M13. |
| 5 | Live classes on the roadmap | **Open.** Blocks nothing until M5. |

`CLAUDE.md` §11 still lists 2, 3 and 4 as open and should be updated.

### New questions raised by ADR-001, deliberately left open

- **BFF vs path routing (M2).** `architecture.md` §3.2 and §4.3 describe two different architectures as if interchangeable. Resolve at M2 kickoff, before auth flows are written.
- **Private network under B-lite (M13).** Server Components fetching Django "over the private network" does not hold if Next.js is on Cloudflare Workers and Django is on Hetzner.

### Documentation defects, not yet corrected in source

- `docs/deployment-strategy.md` §9.3/§14 total the recommended (Mux) stack at ~$62; the line items sum to ~$43. The $62 figure models Cloudflare Stream.
- `docs/adr/002-...` §7.1 audio-mode saving computes to ~$612, not ~$570; §5 B-HA column sums to $152, not $157, and mixes Scenario 1 and Scenario 2 figures.
- Neon is modelled at $15 throughout, against the documents' own derivation of ~$19–20.
- Mux's 1/10 audio rate is claimed for a playback *mode*; it appears to apply to audio-only *assets*. Untagged and unsourced — verify before budgeting.
- `Brainstormv1.md` is cited by section throughout `deployment-strategy.md` and is not in the repository.

---

## Next milestone: M7 — Learning Experience

Enrolment, `LessonProgress`, resume logic, and the lesson player that ties
M5's video to M6's subtitles.

Carried in:

- **ADR-014 §3's risk lands here first.** An interactive transcript — "click a
  line, seek the video" — is the most likely next reader of segments, and it
  must apply the same `APPROVED` filter. The structural guard will stop it
  being written outside the transcripts app; it will not stop a second
  unfiltered query inside one.
- **ADR-011 applies** the moment progress state starts deciding anything.
- **Two visibility gaps are now overdue.** Nothing tells an instructor that a
  media asset failed (M5) or that a transcript is waiting for review (M6).
  Both belong with notifications in M11, and both are "visible if you check"
  until then.

**Still blocking M8:** the payment provider decision (CLAUDE.md §11 #1); the
webhook signature timestamp (ADR-013 §6); and the `billing:` namespace
(ADR-015 §5).

**Still blocking a self-serve trial in M9:** the trial scoping rule
(ADR-010 §2).

### Branch tidy-up, outstanding since M0

Five branches with overlapping history and nothing merged to `master`:
`chore/untrack-planning-docs` (PR #1), `feat/m0-foundations`,
`feat/m1-backend-foundation`, `feat/m2-authentication`, `feat/m3-catalogue`.
Worth resolving before M4 adds a sixth.

## Earlier next-action notes

1. Confirm CI passes on GitHub for `feat/m0-foundations`. The type-check fix in
   `36be0e9` has not yet been *observed* passing — it is the last unverified
   thing in M0, and only GitHub can show it.
2. Start **M1 — Backend foundation**: core app, DRF, `drf-spectacular`,
   `/healthz`, Problem Details error shape, structured logging with
   `request_id`.
3. **Answer the custom-User ordering question before writing the `core` app.**
   It is the first decision M1 needs and the most expensive one to get wrong.

### Carried into M1, recorded so it is not rediscovered

- **Custom User ordering.** M1 builds a `core` app with an audit model; M2
  builds the custom User. As written, M1's first migration lands before the
  custom model exists. Either `AUTH_USER_MODEL` and a minimal `User` move into
  M1 ahead of `core`, or M1 ships only abstract base models. Decide at M1
  kickoff. `make migrate` currently refuses, which buys the time to decide.
- **`citext` for email** (architecture.md §5.2) does not exist in Django 5.2 —
  `CITextField` was removed in the 5.x line. Use `UniqueConstraint(Lower(...))`
  or a non-deterministic collation at M2.
- **UUIDv7** (architecture.md §5.2) needs PostgreSQL 18; the target is 16. Use
  UUIDv4 unless the Postgres version changes.
- **BFF vs path routing** stays genuinely open. The `afterFiles` rewrite
  ordering in `next.config.ts` keeps both possible — a Route Handler under
  `src/app/api/` wins, anything else falls through to Django.
- **Gunicorn `timeout` vs Server-Sent Events** (ADR-002 §7.4) are in direct
  tension. Revisit when the first SSE endpoint exists.
