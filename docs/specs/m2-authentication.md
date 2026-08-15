# Spec: M2 — Authentication & Accounts

**Status:** Draft, awaiting approval. No code written.
**Milestone:** M2 (`docs/architecture.md` §10)
**Prerequisites:** M0, M1 complete.

---

## Assumptions I'm making

Correct any of these now, or the spec proceeds on them.

1. **Web only.** No native app, so no token-exchange endpoint (§4.2 "when to revisit").
2. **Session cookies, not JWT.** Settled in `architecture.md` §4.2 and invariant 9. Not reopened here.
3. **Email/password only.** No OAuth providers — §1.2 puts those in Phase 2.
4. **Roles are fixed at three:** `STUDENT`, `INSTRUCTOR`, `ADMIN` (§4.4). No custom roles, no groups.
5. **Registration self-serves the STUDENT role only.** Instructor and admin are granted, never claimed — `INSTRUCTOR_PROFILE.approved_at` and `approved_by` in §5.1 imply an approval flow.
6. **Email delivery uses Django's own email framework** over SMTP (Mailpit locally). Resend is reachable by SMTP, so no provider adapter is required yet and invariant 4 is not engaged until we call a vendor HTTP API.
7. **No entitlement logic.** `GET /auth/me/` ships without the `access` object until M4 builds the resolver.

---

## Objective

Let a person create an account, prove they own the email address, sign in and out,
and recover from a forgotten password — with sessions that an administrator can
revoke instantly.

Every later milestone depends on this: M3 scopes courses to an instructor, M4
resolves entitlement for a user, M10 audits who did what. A weakness here is not
contained to M2.

**The single most important constraint**, from `architecture.md` §10 M2: the
custom `User` model must exist **before the first migration is ever applied**.
The `make migrate` guard from M0 has been refusing all through M1 precisely to
protect this. M2's first task is the User model, and nothing else may precede it.

---

## Threat model

Five minutes of thinking like an attacker, per the security skill. This drives
the test list, not a generic checklist.

### Trust boundaries

| Boundary | Untrusted input |
|---|---|
| `POST /auth/register/` | email, password, and anything else the client sends |
| `POST /auth/login/` | credentials, at any rate the attacker likes |
| `POST /auth/password/reset/` | an arbitrary email address |
| Verification / reset links | a token that arrived by email, possibly forwarded or leaked |
| Session cookie | replayed, stolen, or held long after it should be |

### Assets

Credentials, the session, the user's email address, and — most valuable — the
`role` field. An attacker who can set their own role owns the platform.

### STRIDE, applied

| Threat | Concrete here | Control |
|---|---|---|
| **Spoofing** | Credential stuffing against `login/` | `django-axes` lockout + 10/hour/IP throttle (§6.4) |
| **Tampering** | Client sends `role: "ADMIN"` in the registration body | Serializer accepts a strict field allowlist; `role` is never writable |
| **Repudiation** | "I never changed that password" | Auth events logged structurally with `request_id` (M1 T6) |
| **Information disclosure** | Probing which emails have accounts | Uniform responses on register and reset; reset always `202` |
| **Denial of service** | Argon2 is deliberately expensive; unlimited login attempts burn CPU | Throttles on every auth endpoint before hashing |
| **Elevation of privilege** | Verification token guessed, replayed, or reused | Store the token **hash**, single-use, time-limited |

### Abuse cases — these become the first tests

1. Register with an email that already exists → response is indistinguishable from a new registration.
2. Request a reset for an address with no account → `202`, same shape, comparable timing.
3. Send `role: "ADMIN"` / `is_staff: true` in the registration body → silently ignored.
4. Reuse a verification or reset token that has already been consumed → rejected.
5. Use a token past its expiry → rejected.
6. Log in with the wrong password N times → locked out, and the lockout is not bypassed by changing the User-Agent.
7. Log in as an unverified user → decide (open question 4).
8. Read another user's profile via `/auth/me/` by manipulating an id → there is no id parameter; `me` is derived from the session only.

---

## Success criteria

Specific and testable. M2 is done when all of these hold:

- A new account can be created, verified by email, signed into, and signed out.
- A forgotten password can be reset end to end, and the old password stops working.
- `GET /auth/me/` returns the authenticated user, and `401`/`403` otherwise.
- Deleting a session row logs that user out immediately (the revocation property that justified sessions over JWT).
- **Every abuse case above has a test that fails without its control.**
- Coverage: permissions and scoping ~95% (§8.1). Auth services ~85%.
- `manage.py makemigrations --check` is clean; the migration guard now passes because a custom `User` exists.
- `check --deploy` clean; ruff, tsc, eslint clean; schema and generated types regenerated (invariant 16).

---

## Scope

### In

| Area | Detail |
|---|---|
| `User` | UUID PK, email as the login field, `role`, `is_email_verified`, no `username` |
| Profiles | `StudentProfile`, `InstructorProfile` (§5.1) |
| Session auth | Argon2 hashing, DB-backed sessions, HttpOnly/Secure/SameSite=Lax |
| Endpoints | register, login, logout, verify-email, resend-verification, password reset + confirm, password change, `me` (§6.2) |
| Brute force | `django-axes` |
| Throttles | Per-endpoint scopes from §6.4 |
| Frontend | Login, register and reset flows; session cookie working same-origin |

### Out, deliberately

- **Entitlements** — `/auth/me/` ships without `access` until M4.
- **Trials** — `TRIAL_CLAIM` and abuse fingerprinting are M9.
- **OAuth, 2FA** — Phase 2 and M10 respectively.
- **Instructor approval workflow** — the profile and its `approved_at` field exist; the admin flow is M10.
- **Django Admin** — stays unrouted until hardened in M10.

---

## Commands

Unchanged from M1. `make migrate` becomes usable for the first time.

```
make dev            start the stack
make test           full suite
make lint           ruff + tsc + eslint
make migrate        apply migrations   (guard passes once User exists)
make types          regenerate schema, then frontend types
make check-deploy   manage.py check --deploy
```

## Project structure

```
backend/apps/accounts/
    models.py       User, StudentProfile, InstructorProfile
    managers.py     UserManager — email instead of username
    services.py     writes: register, verify, reset, change password
    selectors.py    reads
    serializers.py  I/O shape only
    views.py        thin HTTP
    urls.py
    migrations/
frontend/src/app/(auth)/    login, register, reset pages
```

Layering per invariant 2: writes in `services.py`, reads in `selectors.py`,
HTTP in `views.py`, shape in `serializers.py`. A view containing an `if` about
business state is a bug.

## Testing strategy

`pytest` + `pytest-django`, `factory_boy` for factories, `freezegun` for token
expiry boundaries. Unit tests under `tests/unit/`, request-level under
`tests/integration/`.

Every endpoint gets its negative case — wrong user, wrong role, unauthenticated
— per the definition of done. The abuse cases above are the specification.

## Boundaries

**Always:** hash tokens before storing; scope every queryset to the requesting
user; run the full suite before commit; regenerate schema and types when the API
changes.

**Ask first:** any new dependency; any change to the auth strategy; anything
touching the entitlement or billing model.

**Never:** log a password, token or session key; return whether an email is
registered; accept `role`, `is_staff` or `is_superuser` from a request body;
weaken a control to make a test pass.

---

## Open questions — these block implementation

### 1. BFF or path routing? *(blocks the frontend half)*

`ADR-001` §2.1 deferred this to M2 kickoff and it can no longer be deferred.
`architecture.md` §3.2 describes the browser talking only to Next.js, which
proxies to Django. §4.3 option B describes the browser reaching Django directly
for `/api/*`. These are different architectures.

The rewrite currently in place is compatible with both. The question is whether
**login and other mutations must traverse a Next.js Route Handler**, or go
straight through the rewrite to Django.

**Recommendation: straight through the rewrite.** Django already sets the
session cookie and issues the CSRF token; a Route Handler in between would have
to forward both faithfully and would add a hop that only makes the cookie
handling easier to get wrong. Add Route Handlers later only where a genuine
backend-for-frontend concern appears — composing several calls into one page
render, or hiding an internal detail.

### 2. `citext` is gone. What replaces it?

`architecture.md` §5.2 specifies `citext` for email so that `User@x.com` and
`user@x.com` are the same account. Django removed `CITextField` in the 5.x line.

- **A. `UniqueConstraint(Lower("email"))`** plus normalising to lowercase on
  write. Explicit, portable, and the constraint is visible in the schema.
- **B. A non-deterministic collation** on the column. Closer to the original
  intent, makes every lookup case-insensitive automatically, but it is a
  Postgres-specific migration and harder to reason about later.

**Recommendation: A.** It is explicit at the point of use, and invariant 11 is
satisfied because the guarantee still lives in the database.

### 3. Is `AuditLog` in M2?

`ADR-003` §4 assigned it to M2 — but only because it must come *after* the
custom `User`, which was the constraint at the time. Nothing writes an audit row
until M10.

**Recommendation: defer to M10** and amend ADR-003 with a short note. Building a
table now that nothing reads or writes for eight milestones is speculative, and
the ordering constraint it was protecting is satisfied the moment `User` lands.
Say if you would rather keep it in M2 as originally written.

### 4. Can an unverified user log in?

Not specified anywhere. Two coherent answers:

- **A. Yes, but unverified.** They can sign in and see a "verify your email"
  state. Better onboarding; `is_email_verified` gates trial start in M9.
- **B. No.** Login fails until verified. Simpler to reason about, worse if the
  email is delayed or lands in spam.

**Recommendation: A.** §7.1 requires verification before *trial*, not before
login, and blocking login on an email that has not arrived is a common way to
lose a signup. The gate belongs at the point the abuse actually matters.

### 5. When are profiles created?

Eagerly on registration, or lazily on first access?

**Recommendation: eagerly, in the registration service, inside the same
transaction.** A user without a profile is a null check in every consumer
forever.

---

## Task outline

Ordering is dependency-driven. **T1 is not negotiable** — everything else waits
on it, because the first migration fixes `AUTH_USER_MODEL` permanently.

| # | Task | Depends on |
|---|---|---|
| T1 | Custom `User` + manager + **first migration** | — |
| T2 | Argon2, session settings, `django-axes` | T1 |
| T3 | Profiles, created on registration | T1 |
| T4 | Register + email verification (hashed, single-use, expiring tokens) | T2, T3 |
| T5 | Login / logout, throttles, lockout | T2 |
| T6 | Password reset + confirm + change | T4 |
| T7 | `GET /auth/me/` (no `access` object) | T5 |
| T8 | Throttle scopes from §6.4, applied and tested | T4–T7 |
| T9 | Frontend login / register / reset flows | T7 |
| T10 | Regenerate schema + types; ADR for the settled questions | all |

---

## What I would deliberately not build

- A permissions framework. Three roles and object-level `get_queryset()`
  filtering (§4.4) is the whole requirement; a policy engine is not.
- Custom session storage. Django's DB backend is already correct and already
  configured.
- A generic token abstraction. Verification and reset are two token types, and
  two concrete implementations are clearer than one abstraction over them.
- Anything touching billing. Open decision #1 remains unresolved and the
  standing rule holds: **do not model billing.**
