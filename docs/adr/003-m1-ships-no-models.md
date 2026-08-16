# ADR-003 — M1 ships no concrete models; the audit log moves to M2

**Status:** Accepted
**Date:** 2026-08-14
**Related:** `docs/architecture.md` §10 (M1, M2), §5.1, §7.2 · `CLAUDE.md` §4.14

---

## 1. Context

`docs/architecture.md` §10 lists M1's objectives as "core app (base models,
exception handler, pagination, audit), DRF configured, `drf-spectacular`,
health checks, structured logging". The word *audit* means an `AuditLog` model,
and §5.1 gives it an `actor_id` foreign key to `USER`.

M2 then says, emphatically: **the custom user model must exist before the first
migration.** Swapping `AUTH_USER_MODEL` after `auth_user` has been created is a
manual table rename plus a hand-written migration-graph rewrite plus every
foreign key in the schema repointed.

Building `AuditLog` in M1 therefore means running the first migration before
the model it depends on exists. The two milestones, read literally and in
order, contradict each other. This was flagged during M0 and recorded in
`docs/STATUS.md`; it is resolved here.

## 2. Decision

**M1 creates no concrete models and no migrations.** The `core` app ships
abstract base models only. `AuditLog` moves to M2, after the custom `User`.

A test asserts `makemigrations --check --dry-run` finds nothing pending, so M1
accidentally acquiring a model fails the build rather than being discovered
later.

## 3. Options considered

**A — M1 ships no concrete models.** Chosen.

**B — Pull a minimal custom `User` into M1**, then build `AuditLog` on it.
Rejected. It trades one expensive mistake for the same mistake in a different
direction: a hastily-shaped `User` is as costly to change later as a swapped
one, and email-as-username, UUID primary key and the role field are exactly the
decisions M2 exists to give proper attention to. Doing them in a milestone
that is about API scaffolding, to satisfy the ordering of a bullet list, is
backwards.

**C — Merge M1 with the first slice of M2.** Rejected. `CLAUDE.md` §10 calls
milestone order non-negotiable, and blurring the boundary loses the property
that makes it useful.

## 4. Consequences

Nothing is lost by waiting. Per §7.2 the audit log records *admin* actions —
manual access overrides, refunds, role changes — none of which exist before
M10. No code between here and there writes an audit row.

M1 producing zero migrations becomes a checkable property rather than an
intention. The `make migrate` guard added in M0 stays active for the whole of
M1, and the fact that it still refuses at the end of M1 is evidence the
constraint held.

The cost is a documented divergence from `architecture.md` §10. That document
is not being edited: `CLAUDE.md` §2 says later ADRs beat earlier documents, and
rewriting the design doc to match every implementation choice would destroy its
value as a record of what was originally intended.

**Carried into M2:** `AuditLog` must be built *after* the custom `User`, not
alongside it. M2's own ordering therefore matters — `User` first, everything
else second.

> **Amended by ADR-005 §3 (2026-08-15).** `AuditLog` moves to **M10**, not M2.
> The ordering constraint above is satisfied the moment `User` lands, but that
> does not mean the table should be built then: nothing writes an audit row
> until the admin actions in M10 exist. The reasoning in this ADR stands; only
> the destination milestone changed.
