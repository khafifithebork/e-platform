# Runbook — admitting people to the private beta

**Status: written, not walked.** Written 2026-10-31 alongside slice 3b-i of
`tasks/plan.md`. No step below has been performed against a real deployment, because
there is no deployment — hosting spend is unapproved (CLAUDE.md §11 row 3). Treat it as
a plan rather than a tested procedure: `rollback.md` found its own §3 wrong the first
time somebody walked it, and `accessibility-verification.md` says to assume the same.
Assume this one has that kind of error in it too.

**The admission gate is off by default.** `BETA_INVITATION_REQUIRED` defaults to
`False`, so on a fresh environment registration is open and nothing here is needed.
Turning it on is a release admission policy and needs its own approval — slice 3a's own
entry in `tasks/plan.md` says so in terms.

---

## 1. What an invitation is, and what it is not

An invitation says **this email address may create an account**. That is all.

- It is **not** access to content. Access comes from a subscription or an access
  override, and the entitlement resolver does not know invitations exist (invariant 3).
- It is **not** proof the person owns the inbox. Email verification still does that, and
  still has to happen afterwards.
- It is **not** a credential. There is no token or link to send — the record is the
  address itself, so there is nothing to leak and nothing to paste.

Each address is admissible exactly once: the unique constraint is on `Lower(email)`, so
there is one row per person and re-issuing re-opens it rather than adding a second.

## 2. Before you can admit anybody

You need an **active administrator account with a TOTP device**, because the admin site
is behind `django_otp`.

1. The account's `role` must be `ADMIN`, **or** it must be a superuser. Either is
   accepted (`accounts.privileges.is_platform_administrator`). A `createsuperuser`
   account has `role=STUDENT` and still qualifies — that was fixed on 2026-10-31 after
   it turned out to lock the bootstrap account out of issuing the first invitation.
2. Enrol a TOTP device:

   ```
   python manage.py enrol_admin_totp <email>
   ```

   It prints an enrolment QR code. `--replace` swaps an existing device.
3. The admin lives at the path in `DJANGO_ADMIN_PATH`, which is **unset by default** —
   if it is empty the admin is not routed at all (`config/urls.py`). Set it to something
   unguessable in any environment where you need the admin.

**Do not create the learner's account yourself.** You cannot, and should not want to:
`UserAdmin.has_add_permission` returns `False`, because an account made there would have
no usable password and no verification email. Admission works the other way round — you
issue an invitation, and the person registers normally.

## 3. Issuing an invitation

In the admin, under **Accounts → Beta invitations**, add one. You must supply:

- the **email address**, exactly as the person will type it (casing does not matter)
- a **reason**, which is required and must say something

The reason is not ceremony. It is the only field that answers "why is this person in the
beta" six weeks later, to somebody who was not there — the same argument ADR-010 §5 makes
about access overrides becoming permanent unexplained flags.

Saving routes through `accounts.services.issue_invitation`, which writes an audit row
naming you, the address, the expiry and whether the row was re-opened. The invitation
lasts **30 days** (`INVITATION_LIFETIME`).

Then tell the person to register at `/register/` as normal. Nothing is emailed by
issuing an invitation — if you want them to know, you tell them.

## 4. What the person does

1. Registers at `/register/` with their email and a password.
2. Gets a verification **token** by email — a bare token, not a link, because there is no
   configured site URL to build one from (ADR-034). They paste it at `/verify-email/`.
3. Signs in.

The invitation is consumed during registration, atomically with the account. If account
creation fails, the invitation is **not** spent.

**Registration answers the same 202 whatever happens** — invited, never invited, expired,
revoked, or already registered. That is deliberate (§7.1, account enumeration), and it
means **the endpoint will not tell you whether your invitation worked.** If somebody says
registration did nothing, check the invitation's state in the admin rather than inferring
it from the response.

## 5. Revoking an invitation

Use the **revoke** action in the admin. It routes through `revoke_invitation`, writes an
audit row, and is refused if the invitation has already been consumed — at that point an
account exists and revoking the invitation would not remove it.

**To remove access from somebody who already registered, this is the wrong tool.**
Deactivate the account (`is_active`) or change what they are entitled to. Account
deletion is not built and is an open question (ADR-036 §5).

A revoked invitation can be re-issued later; issuing re-opens the same row.

## 6. Giving somebody access without billing

Separate mechanism, and the one to reach for when a beta tester needs to *see content*
rather than merely *have an account*.

`entitlements.services.grant_access_override` takes **days, not an end date** — a support
person thinks "give them two weeks", and a duration makes two failures impossible: an
override that expired before it was created, and one that never ends. Bounded at
**1–90 days** (`ACCESS_OVERRIDE_MAX_DAYS`), and a reason is required.

Self-grants are allowed and audited like any other. ADR-010 §5's reasoning is that
blocking them would be theatre — an administrator who wants free access can grant it to
a second account they control — so the control that works is the one that makes it
visible.

## 7. When something looks wrong

| Symptom | Where to look |
|---|---|
| "I registered and nothing happened" | The invitation's state in the admin. The endpoint cannot tell you, by design |
| "I never got the token" | `notifications` — and remember it is a token, not a link |
| Invitation looks consumed but the person has no account | Should be impossible: consumption is atomic with account creation. If you see it, that is a bug worth a ticket, not a retry |
| Re-issuing is refused | The invitation is consumed, so an account exists. Look the account up instead |
| An admin cannot issue | Role, `is_active`, and the TOTP device. All three are required |

## 8. What this runbook does not cover

- **Turning the gate on.** A deployment decision with its own approval.
- **Bulk admission.** There is no bulk path; issue them one at a time or write a
  management command, which does not exist and would need an actor argument that is
  self-asserted rather than authenticated.
- **Anything about billing.** There is no payment provider (CLAUDE.md §11 row 1).
