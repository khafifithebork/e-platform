# M13 — Deployment & CI/CD

**Status:** 5.5 settled 2026-08-26 — build the unblocked half (T2–T6).
5.1–5.4 remain open; T7–T10 do not start until they are answered.
**Branch:** `feat/m13-deployment`
**Depends on:** M0 (containers), M12 (CI gates)

---

## 1. Objective

**A merge to `master` reaches a running environment without anybody typing a
deploy command, and a bad deploy can be undone by somebody who has already
practised undoing one.**

architecture.md:1057 lists: `render.yaml`, staging on a Neon branch, a
migration pre-deploy step, automated deploys on merge, a rollback procedure
documented **and rehearsed**, secrets configured, Cloudflare routing and WAF.

---

## 2. M13 cannot start on its own

Three things block it, and none is mine to resolve.

### 2.1 The hosting target is undecided — CLAUDE.md §11 #4

The objective names `render.yaml`. **ADR-002 §6 recommends against Render**,
and ADR-002 is the later document, which §2 says wins. §11 lists the decision
as open, scoped to "M13 only", with the instruction to *containerise so it
stays late-binding*.

That containerising is **done**: both Dockerfiles are multi-stage with a
`runtime` target, and compose runs the same images locally. So the decision is
as cheap now as it will ever be, which is exactly the position ADR-002 §6 asked
for.

| Option | Frontend | App tier | Scenario 1 | Ops |
|---|---|---|---|---|
| **B — Render** | container $7 | 2 services $14 | **$50/mo** | 1–3 h/mo |
| **B-lite — edge + VPS** ⭐ ADR-002 | Workers $5 | 1× Hetzner CX33 $10 | **$44/mo** | 3–6 h/mo |
| **B-HA — redundant VPS** | Workers $5 | 2× CX33 + LB $27 | ~$61/mo | 4–8 h/mo |

ADR-002 §6 recommends **B-lite**, and is explicit that the tiebreaker is not
cost — it is $6/month — but what the owner wants from the project: *"ship
fastest and never think about a server"* versus *"learn DevOps properly"*.

**That is a preference, not a technical finding. It is not an agent's call.**

### 2.2 Every option is new spend — CLAUDE.md §5

"Adding a new paid service, or any change that alters the monthly bill"
requires explicit approval before code. Every option above adds Neon, a host,
and eventually Mux and Deepgram. **Nothing in M13 should be provisioned before
that approval, in writing, with the option named.**

### 2.3 The spike ADR-002 required was never run

ADR-002 §3 Move 2 says of running Next.js on Workers: *"The Next.js-on-Workers
adapter (OpenNext) is mature but not identical to running `next start`. Some
Node APIs and long-running route handlers are constrained. **Validate this with
a spike in M0 before committing** — an hour of work that de-risks the
decision."*

**It was not run.** There is no spike document, no OpenNext configuration, and
no record of the question being answered. B-lite and B-HA both depend on it.

This is the fifth instance of the pattern ADR-023 §1 names — a document
describing work that was never done — and the first one found *before* building
on top of it rather than after.

---

## 3. What can be built without the decision

Genuinely target-agnostic, and worth doing whichever way §2.1 goes:

1. **The CSP report endpoint** M12 handed over. A view that accepts
   `application/csp-report`, rate-limited, that logs rather than stores. Until
   it exists, the report-only policy reports to nowhere.
2. **A migration pre-deploy step** as a script with an exit code, not a
   platform hook. `render.yaml`, a Dokploy job and a GitHub Action can all call
   the same thing.
3. **A release image built and tagged in CI**, without pushing it anywhere. The
   push needs a registry, which needs an account.
4. **The rollback procedure, written.** Rehearsing it needs a running
   environment; writing down what to do does not, and writing it first is what
   makes the rehearsal a test rather than an improvisation.
5. **A production-settings smoke check** — one command that boots the runtime
   image against production settings and fails on anything `check --deploy`
   catches, so a misconfiguration is caught before a platform is involved.

## 4. What only the owner can do

Stated plainly because it changes what "M13 complete" can mean:

- **Creating accounts** (Neon, Render or Hetzner, a registry) — I will not
  create accounts or enter credentials.
- **Entering secrets** anywhere — platform dashboards, GitHub secrets.
- **DNS and Cloudflare WAF rules**, which touch a live domain.
- **Approving the bill.**

I can write every configuration file these consume, and verify them as far as
anything can be verified without an account.

---

## 5. Decisions to settle

| # | Question | Blocks |
|---|---|---|
| 5.1 | **Hosting: B, B-lite or B-HA?** ADR-002 recommends B-lite; the tiebreaker is what you want from the project | almost all of M13 |
| 5.2 | ~~**Approve the monthly spend**~~ — **approved 2026-08-29 for B-lite**, at the figures ADR-002 §5 records: **$44/month at Scenario 1**, ~$120 at Scenario 2. Provisioning is unblocked; **account creation and payment details remain the owner's to do** | was §5 gate |
| 5.3 | **Run the OpenNext spike now?** Required before B-lite or B-HA can be committed to | 5.1, if B-lite |
| 5.4 | **Celery Beat: in the worker at one replica, or platform cron?** CLAUDE.md §11 #3, scoped to M0 and M13 | the worker's deploy shape |
| 5.5 | **Scope check:** should M13 shrink to §3 and hand provisioning to M13b once the answers exist? | the shape of this milestone |

**Recommendation on 5.5:** yes. Build §3 now, and let the platform work start
when 5.1 and 5.2 are answered. The alternative — waiting — leaves the CSP
policy reporting to nowhere and M12's handover unclosed for no reason.

**No recommendation on 5.1.** ADR-002 already made the technical case and
concluded the tiebreaker is a preference about how you want to spend your time.
Restating its recommendation as mine would be presenting your own document back
to you as advice.

---

## 6. Task outline — conditional

**Unblocked, buildable now:**

| # | Task |
|---|---|
| T1 | This spec + ADR-024 once 5.1–5.5 are answered |
| T2 | CSP report endpoint, throttled, logging not storing |
| T3 | Migration pre-deploy script, platform-agnostic |
| T4 | Release image built and tagged in CI |
| T5 | Production smoke check against the runtime image |
| T6 | Rollback procedure, written |

**Blocked on 5.1 and 5.2:**

| # | Task |
|---|---|
| T7 | Platform configuration — `render.yaml` **or** Dokploy compose + Caddy |
| T8 | Staging on a Neon branch; `pg_trgm` verified there (M12 handover) — **preparation done; the verification itself needs the branch to exist** |
| T9 | Deploy on merge; production as one approved action |
| T10 | Rollback **rehearsed**; production load baseline (M12 handover) |

---

## 7. Not in M13

- **No account creation, no secrets entered, no DNS changes.** §4.
- **No provisioning before §5.2 is answered in writing.**
- **No `render.yaml` written on the assumption that Render wins.** It is one
  line of §11 away from being the wrong file, and writing it would quietly make
  the decision.
- **The static public surface** (ADR-002 Move 1, "not optional either way") is
  a Next.js routing-group change over marketing routes that **do not exist**.
  It collides with the frontend-ownership question for the fourth time and is
  not smuggled in here.
