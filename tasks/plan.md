# Private beta production-readiness plan

Date: 2026-10-23. Status: proposed implementation plan; approval required per batch.
Tasks are tracked in `tasks/todo.md`. No earlier task plan existed at these paths.

## Confirmed by the owner

- First release: private beta without payments.
- Public homepage and catalogue remain visible; learner admission is by invitation.
- Use the lean hosting direction and verify current prices before any purchase.
- Domain not chosen yet. No purchase, deployment or production-setting edit authorized.

Keep Django session authentication, the single entitlement resolver, provider
adapters, generated API types and static public routes. Do not introduce checkout,
self-service trials, a second authentication system, or new dependencies.

## Evidence and unresolved decisions

- Registration currently permits any valid email. A private-beta label or hidden
  link cannot implement admission control. `UserAdmin` intentionally cannot add
  accounts; do not use it as an invented onboarding mechanism.
- Proposed admission: database-backed email invitations, the existing signup
  and email-verification flow, and generic registration responses. An invitation
  permits signup only; it never directly grants course access. Expiry is explicit,
  not an invented default. Service guards must cover non-HTTP callers too.
- Beta lesson access can use existing administrator-issued, audited, time-limited
  access overrides within their existing bounds. Never simulate paid subscriptions
  or weaken `resolve_access`. Confirm this operator workflow in staging.
- The budget/spend records conflict: AGENTS says unapproved; STATUS and the
  provisioning worksheet record an older lean approval. Today's answer authorizes
  verification and planning, not a purchase. Reconcile the records only after an
  explicit costed approval. Do not silently rewrite the accepted ADR-002 baseline.
- The current pipeline expects separate staging and production destinations.
  Their topology and incremental costs remain undecided. Do not point both at
  production or remove staging to make a low estimate appear viable.
- Real video and transcription adapters are absent. Decide whether the first
  beta includes video before selecting/integrating a paid provider. Do not serve
  fake provider responses as production functionality.
- PR #120 (missing-asset budget guard) is green and open. It is not merged by this
  plan. This branch starts from master after PR #119.

## Current cost checks (research, not a quote or spend approval)

Checked primary vendor pages on 2026-10-23:

| Component | Verified information | Still needed before provisioning |
|---|---|---|
| Hetzner | Official June price adjustment lists EU CX23 at EUR 5.49/month, excluding VAT and IPv4 | Available SKU/region, current console quote, IPv4, taxes, backup costs and staging arrangement; CX23 is not automatically a replacement for the old CX22 assumption |
| Workers | Free: 100,000 requests/day and 10 ms CPU/invocation; paid minimum USD 5/month; static asset requests free | Measure actual lesson SSR/proxy CPU; a successful build alone does not prove the free plan fits |
| Neon | Free page currently lists 1 GB/project and 100 CU-hours/month/project | Account-specific region/branch quotas, restore retention and suitability for this deployed beta; old 0.5 GB figures are stale |
| R2 Standard | Free allowance: 10 GB-month, 1 million Class A and 10 million Class B operations/month; Internet egress free | Media volume, request volume, independent backup and restore design |
| Resend | Free page lists 3,000 emails/month and 100/day | Verify sender domain and delivery; invitation/signup volumes must fit both limits |
| Domain, backups, staging, media | No verified combined quote | Domain choice, topology, content scope and explicit monthly ceiling |

Sources:
- https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- https://www.hetzner.com/cloud/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://neon.com/pricing
- https://developers.cloudflare.com/r2/pricing/
- https://resend.com/pricing

The Hetzner landing page did not expose selectable live quotes in this read.
The official adjustment provides a reference rate, not availability or a final
invoice. No combined monthly total is claimed. These observations do not change
the architecture, enable vendor features, or authorize exceeding free allowances.

## Ordered implementation slices

Every slice requires its own AGENTS section 7 plan/approval, a small commit,
relevant tests, review and STATUS update. Future file lists are estimates until
their slice is inspected. No task may grow past ten files without escalation.

### 1. Invitation persistence (first proposed implementation batch)

Objective: represent operator-issued beta invitations without exposing any new
API or granting course access.

Files: `backend/apps/accounts/models.py`, a new
`backend/apps/accounts/migrations/0005_betainvitation.py`, new
`backend/tests/unit/test_beta_invitation_model.py`, `docs/STATUS.md`.

Acceptance:
- Normalized invitation emails are case-insensitively unique in the database.
- An explicit expiry and revocation/consumption state support the later admission
  checks. No credentials or invitation email values are written to fixtures in
  environment files or documentation.
- Adding the foundation alone does not change signup behavior or entitlements;
  it is not a private-beta launch deliverable by itself.

Named tests: `test_invitation_email_is_case_insensitively_unique` and
`test_expiry_must_follow_issue_time`.
Verification: run those tests against PostgreSQL; review the new-table migration
and constraints; run Ruff and migration consistency checks. No applied migration
is edited. Dependencies: owner approves the proposed invitation approach and this
batch. Scope: medium, four files.

### 2. Invitation services

Objective: issue, revoke and consume invitations with real actor checks and
transactional guarantees. Review slice 1's final record fields with its approval.
Files: account services, core audit actions, new service tests, STATUS (four files).
Acceptance: only an administrator may issue/revoke; registration consumes an
unexpired, unrevoked invitation atomically; a failed account creation cannot
consume it. Named tests: `test_non_admin_cannot_issue_invitation`,
`test_expired_or_revoked_invitation_is_refused`,
`test_account_failure_does_not_consume_invitation`,
`test_invitation_cannot_be_consumed_twice`.
Verification: real service/database tests including concurrent attempts and audit
rollback, not mocks asserting a service was called. Dependency: 1. Scope: medium.

### 3a. Server-side registration admission

Objective: enforce invitation-only signup for beta without changing authentication.
Files: account services/views, registration integration tests, STATUS (four files).
Acceptance: an invited email can complete normal signup; uninvited, expired,
revoked and duplicate cases preserve the generic response and never send an
unauthorized verification email or create an account. Existing sessions/reset
flows remain intact. Named tests: `test_invited_registration_succeeds`,
`test_uninvited_registration_creates_no_account`,
`test_registration_responses_do_not_reveal_invitation_state`.
Verification: full account/auth tests, direct API tests and existing schema drift
check; regenerate contract/types if the inspected implementation changes them.
Dependency: 2. Scope: medium. This is a release admission policy; approve it
explicitly before applying it to deployed configuration or existing users.

### 3b. Honest signup and operator guidance

Objective: explain invited-only signup and document issuing/revoking invitations,
email verification and existing bounded beta access overrides.
Files: registration UI and its tests, account administration and its tests,
operator runbook (maximum five; split further if needed).
Acceptance: no checkout/trial promise; UI does not disclose invitation state;
operator flow is tested and never uses Django Admin to create a passwordless user.
Verification: component tests, admin role-negative cases, keyboard/mobile review
and staged signup/verification/reset/access-expiry walkthrough. Dependency: 3a.
Scope: medium. Recheck actual admin code before selecting the integration seam.

### Checkpoint A — admission ready for staging

All invitation/registration negative tests pass, no entitlement rule changed,
the normal signup flow works for an invited learner, and uninvited API calls fail
without side effects. Review with owner before deploying any beta gate.

### 4. Approve a costed hosting topology

Owner chooses domain and monthly ceiling; obtain a current EU server quote and
resolve staging isolation, Worker runtime limits and backup costs. Document a
decision and reconcile the two agent briefs together if their approval status
changes. No provider is purchased in this task. Files: provisioning worksheet,
new decision record, STATUS, and the two briefs only if necessary (maximum five).
Verification: source-linked quote and explicit approval; matching agent briefs.
Dependency: domain/quote decisions; can be investigated while slices 1–3 progress.

### 5. Staging provisioning and deployed proof

Owner creates the approved accounts and securely supplies secrets directly to
the target dashboards. Use the existing provisioning worksheet; no secret values
enter code, logs or this plan. Configure an isolated staging environment first.
Split into separate batches: provider setup; runtime/DNS configuration; then
Worker-to-Django smoke verification (at most five files per batch).
Acceptance: production-settings checks and `check_database` pass; migration lock
uses the direct connection; session cookies/CSRF and verification/reset email work
across the real Worker; public routes are static and publish rebuilds are proven.
Verification: existing smoke script plus named browser cases
`staging_session_cookie_round_trip`, `staging_csrf_rejection`,
`staging_password_reset_delivery`, `staging_publish_rebuild`.
Dependencies: 4 and approved production/provider configuration changes.

### 6. Content and media scope

Owner supplies a real beta course and decides video inclusion. If video is in,
select and approve the adapter and its cost before implementation; plan the
upload/signing/playback/transcript slices separately (maximum five files each).
If video is deferred, explicitly approve and test a text-course beta scope.
Acceptance: no fake playback/transcription feature is offered; denied users never
receive usable media tokens; actual lesson content has captions/transcript and
audio-description assessment where applicable. Verification: real upload/playback
and access-denial tests with no media passing through Django. Dependency: scope
decision; provider activation additionally needs 4–5. Policy content and a contact
identity also need owner review before collecting tester data.

### 7. Recovery and monitoring

Split into backup configuration, restore rehearsal and monitoring batches.
Keep each at most five files. Use the deployed staging system first.
Acceptance: database and irreplaceable masters have an approved backup design;
restore is actually executed and documented; a deliberate API/database failure is
detected even when `/healthz` is green. Verify error reporting, worker/Beat health
and alert delivery; rehearse release rollback against that environment.
Verification: recorded `staging_database_restore`, `staging_master_restore` where
media exists, `staging_database_failure_alert`, `staging_release_rollback`.
Dependencies: 5; media backup checks additionally need 6. New services/costs require
separate approval. Do not claim a file in storage is a tested recovery procedure.

### Checkpoint B — releasable private beta

Admission, staged flows and recovery are proven; remaining issues have owners.
Human review covers screen readers, native text-only zoom, real phones/other
browsers and actual media. Domain identity and privacy/terms text are supplied.
Review dependencies/audits again at release time. No self-service trial or paid
subscription is promised or enabled.

### 8. Approved deployment and limited opening

Configure GitHub production required reviewers before enabling the deployment
switch. Review the exact staged commit and obtain explicit production approval.
Deploy, smoke-test, then admit the agreed tester cohort. Record how to stop
onboarding, revoke access and roll back. No guessed cohort size or performance
thresholds; agree those from staging measurements and owner expectations.
Dependencies: Checkpoint B, production account/secret setup and explicit approval.
Verification: recorded signup/login/lesson/progress/resume/logout/expiry smoke,
alerts received, backups checked and release/rollback identifiers retained.

## Not in this beta

Real billing and payment-provider selection, self-serve trials, public learner
signup, instructor product UI, new search infrastructure, or another redesign.
Their existing milestone/approval gates remain. No work here weakens security,
changes the entitlement model, or treats free-tier quotas as a guaranteed SLA.
