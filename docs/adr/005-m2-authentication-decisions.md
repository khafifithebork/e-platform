# ADR-005 — M2 authentication decisions

**Status:** Accepted
**Date:** 2026-08-15
**Related:** `docs/architecture.md` §3.2, §4.2, §4.3, §5.2, §7.1 · `docs/adr/001-architecture.md` §2.1 · `docs/adr/003-m1-ships-no-models.md` · `CLAUDE.md` §4.9, §4.11

---

## 1. Context

`docs/specs/m2-authentication.md` raised five questions that blocked
implementation. Four are settled here; the fifth amends ADR-003.

## 2. Decisions

### 2.1 No BFF layer — the browser reaches Django through the rewrite

ADR-001 §2.1 deferred this to M2 kickoff, and M2 is where deferring stops being
possible.

`architecture.md` §3.2 describes a backend-for-frontend: the browser talks only
to Next.js, which talks to Django. §4.3 option B describes path routing: the
browser reaches Django directly for `/api/*`. The document presents them as
interchangeable and they are not.

**Decision: mutations go straight through the rewrite to Django.** Route
Handlers are added later only where a genuine BFF concern appears — composing
several API calls into one page render, or hiding an internal detail from the
browser.

**Why.** Django already issues both the session cookie and the CSRF token. A
Route Handler in the middle must forward both faithfully in both directions,
and every additional hop is somewhere for that to go subtly wrong — the exact
failure class §4.3 warns about when rejecting subdomains-plus-CORS. It also
costs a hop on every mutation for no benefit at this scale.

**Consequence.** The frontend calls `/api/v1/...` on its own origin and the
rewrite carries it. Nothing about this forecloses adding Route Handlers later;
the `afterFiles` rewrite ordering established in M0 means a Route Handler that
genuinely exists takes precedence automatically.

### 2.2 Case-insensitive email without `citext`

`architecture.md` §5.2 specifies `citext` so that `User@x.com` and `user@x.com`
are one account. Django removed `CITextField` in the 5.x line, so the document
cannot be followed literally.

**Decision: normalise to lowercase on write, and enforce it in the database
with `UniqueConstraint(Lower("email"))`.**

**Why not a non-deterministic collation.** It is closer to the original intent
and makes every lookup case-insensitive automatically, but it is a
Postgres-specific migration that is easy to apply and hard to reason about
later. The functional constraint is visible in the schema and obvious at the
point of use.

**Consequence, stated plainly because it looks redundant.** The `email` field
also carries `unique=True`. That is not belt-and-braces: Django's `auth.E003`
check requires `USERNAME_FIELD` to be unique, and an *expression* constraint
does not satisfy it — only a field-level one does. So the table carries two
unique indexes, one exact and one on `Lower(email)`. The alternative was
silencing a system check, which is worse. Invariant 11 is satisfied either way:
the guarantee lives in the database, not only in a Python validator.

### 2.3 Unverified users may sign in

Not specified anywhere in the design documents.

**Decision: a user may log in before verifying their email, in an unverified
state.** `is_email_verified` gates the actions that need it.

**Why.** §7.1 requires verification before *trial*, not before login. Blocking
login on an email that has been delayed or filed as spam loses signups at the
worst possible moment, and the gate belongs where the abuse actually matters —
which M9 will enforce at trial start.

### 2.4 Profiles are created eagerly

**Decision: the registration service creates the profile inside the same
transaction as the user.**

A user without a profile would be a null check in every consumer, forever, to
save one row at signup.

## 3. Amendment to ADR-003 — `AuditLog` moves to M10

ADR-003 §4 assigned `AuditLog` to M2. That was correct given what it was
protecting: the model has a foreign key to `User`, so it had to come after the
custom user model, and in M1 that meant "not yet".

That constraint is satisfied the moment `User` lands in M2. It does not follow
that the table should be *built* in M2. Per §7.2 an audit row records admin
actions — overrides, refunds, role changes — none of which exist until M10.

**`AuditLog` moves to M10, where the first thing that writes to it is built.**
ADR-003 is not superseded; its reasoning stands and only the destination
milestone changes.

## 4. Consequences

The frontend has no server-side auth layer to build, which removes work from
M2's frontend tasks and removes a place for cookie handling to go wrong.

The `email` column carries two unique indexes. On a table of this size that is
not a cost worth optimising, but it should not surprise anyone reading the
schema.

Any code that assumes a logged-in user has a verified email is wrong. The
correct check is `is_email_verified`, and M9 depends on that distinction.
