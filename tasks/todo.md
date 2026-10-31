# Private beta readiness tasks

Plan: `tasks/plan.md`. Owner decisions recorded 2026-10-23.
Unchecked means not completed, not permission to implement or deploy.

- [x] Confirm private beta without payments.
- [x] Confirm public pages remain visible; learner admission is by invitation.
- [x] Confirm lean cost verification; domain remains unchosen.
- [x] Inspect registration, operator account creation, existing access overrides,
  provisioning and available primary-source pricing.
- [x] Approve slice 1 and its invitation approach.
- [x] 1. Invitation persistence and database constraints (1,604 backend tests passed).
- [x] Stop before slice 2: approve and complete dependency security repairs.
  Both audit jobs are green on `master` (PRs #125, #126, #127). DRF, Next.js and
  Sentry were upgraded; the frontend chain needed a wrangler bump rather than an
  overrides pin, because an override cannot reach a publisher-inlined copy.
- [x] 2. Authorized, audited invitation services and atomic consumption
  (26 invitation tests; full backend suite green). Registration is untouched —
  nothing reads these invitations yet, so no admission behaviour is live.
- [ ] 3a. Server-side registration admission and negative API tests.
- [ ] 3b. Honest signup UI and tested operator onboarding runbook.
- [ ] Checkpoint A: admission ready for staging, reviewed with owner.
- [ ] 4. Select domain, obtain current quote, approve topology and spending cap.
- [ ] 5. Provision isolated staging; prove cookies, CSRF, email and static rebuilds.
- [ ] 6. Decide media scope, supply real content and policy/identity text.
- [ ] 6a. Implement and verify approved media delivery, or approve text-only beta.
- [ ] 7a. Approved backup design and implementation.
- [ ] 7b. Executed database/media restore and release rollback rehearsals.
- [ ] 7c. Real monitoring, error reporting and failure-alert delivery.
- [ ] Checkpoint B: human accessibility/device/media review and release signoff.
- [ ] 8. Configure production approval gate; obtain explicit deployment approval.
- [ ] Deploy staged revision, smoke-test and admit the agreed tester cohort.

Separate integration item: PR #120 is green and open; merge needs explicit
instruction. No purchase or deployment has been authorized by this plan.
