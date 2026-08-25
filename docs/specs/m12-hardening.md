# M12 — Hardening & Test Completion

**Status:** decisions settled 2026-08-25 (ADR-022). T2 approved to start.
**Branch:** `feat/m12-hardening`
**Depends on:** everything M0–M11 shipped

---

## 1. Objective

**Close the gap between what this codebase claims about itself and what is
measured.** M12 is the milestone where the §8.1 coverage targets stop being
aspirations, the dependency audit architecture.md promised actually runs, and
the security headers that were assumed present get written.

---

## 2. Two things found before writing this spec

### 2.1 There is no CSP to tighten

architecture.md:1054 says "CSP tightened". **There is no Content-Security-Policy
anywhere** — not in Django settings, not in middleware, not in
`next.config.*`. The task is *introduce*, not tighten, and that is a
materially larger piece of work with a real risk of breaking pages.

It also has two homes, not one. Next.js serves the product's HTML; Django
serves the admin site and DRF's browsable API, which are also HTML and are the
higher-value target (M10 routed the admin precisely because it is).

### 2.2 The dependency audit was never added

architecture.md:848 specifies "Renovate for updates, `pip-audit` and
`npm audit` in CI, lockfiles committed, **CI fails on high-severity**". CI runs
two jobs, `backend` and `frontend`, and **neither audits anything**. There is
no CodeQL either.

This is ADR-021 §1's shape again — a document describing a control that was
never built, reading as done to anyone holding the document.

### 2.3 What *is* measured today

One coverage gate: `apps.entitlements.resolver` at `--cov-fail-under=100` with
branch coverage. Nothing else. The §8.1 targets for permissions (~95%),
services (~85%) and billing webhooks (100%) have never been measured, so
whether they are met is unknown rather than assumed.

---

## 3. Decisions to settle before T2

Four questions. Three of them are §5 dependency gates.

> All four settled on the recommendation. `pip-audit`, `django-csp` and `k6`
> approved. ADR-022 records the reasoning.

### 3.1 Which §8.1 targets get a CI gate

Measuring is cheap; gating is a commitment. A gate that fails on an unrelated
refactor gets raised until it means nothing, which is worse than no gate.

**Recommendation:** measure all of §8.1 and report it, but gate only what §8.1
calls 100%: the entitlement resolver (already gated), and **trial lifecycle
and billing webhooks are deferred to M8/M9** because neither exists yet.
Permissions and services get a **reported floor** — a number in the CI log and
in STATUS — not a build failure. Revisit once there is a history to say what a
normal fluctuation looks like.

### 3.2 `pip-audit` and `npm audit` in CI — **new dependency, §5 gate**

`npm audit` ships with npm; nothing to add. `pip-audit` is a new dev
dependency.

**Recommendation:** add `pip-audit` as a dev dependency and run both, failing
on **high and critical only**. Failing on moderate turns a security gate into
a nuisance that gets `|| true`-d within a month, which is the failure mode
worth avoiding. Renovate and CodeQL are **out of scope** — both are repository
configuration rather than code, and CodeQL in particular changes what runs on
every push.

### 3.3 How CSP is delivered — **possible new dependency, §5 gate**

| Option | Cost |
|---|---|
| **A — `django-csp` + Next.js `headers()`** | A maintained implementation, nonce support, report-only mode. One new dependency. |
| **B — hand-rolled middleware + Next.js `headers()`** | No dependency. Nonce handling and report-only are ours to get right, and CSP is unforgiving. |
| **C — Cloudflare edge rules only** | No code at all, and no protection in development or CI, so nobody finds out a directive is wrong until production. |

**Recommendation: A.** CSP is a control where a subtle mistake is either an
unprotected site or a blank page, and Django's admin uses inline styles that
need a nonce. The dependency is small, widely used, and confined to one
middleware.

**Report-only first**, in both places. A CSP shipped in enforcing mode without
a report period is how a login form silently stops working.

### 3.4 What the load test is, and what "pass" means — **new dependency, §5 gate**

architecture.md:1054 says "load test the catalogue and player endpoints".
There is no tool and no target number.

**Recommendation:** `k6`, scripted against the catalogue list, course detail
and **search** — search is M11's ranked query over a GIN index and the most
expensive anonymous endpoint in the product. **No pass/fail threshold is
invented.** The deliverable is a recorded baseline: p50, p95 and error rate at
a stated concurrency, on stated hardware, written into STATUS. A threshold
guessed now is a number nobody can defend; one derived from a baseline is a
decision.

If a tool is unwelcome, the fallback is a `locust` file or a plain script —
but the recommendation is the one with a text output that can be committed.

---

## 4. Abuse cases — these become the first tests

1. A CSP directive that would break an existing page is caught **before**
   enforcement, by a report-only period with somewhere to send reports.
2. The admin site still works under CSP — it uses inline styles, and a policy
   without a nonce silently blanks it.
3. A high-severity dependency advisory **fails CI**, and the check is provoked
   against a known-vulnerable pin rather than trusted because it printed
   "clean".
4. The coverage gate fails when coverage drops, provoked by deleting a test —
   a gate nobody has watched fail is ADR-006's inert control.
5. Load-test numbers are recorded with the hardware and concurrency that
   produced them; a number without its conditions is not a baseline.
6. `check --deploy` stays clean with CSP added.
7. No security header regresses: HSTS, nosniff, frame options and the rest are
   asserted together, swept rather than spot-checked.

---

## 5. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR-022 | four answers |
| T2 | Measure §8.1 coverage; record the real numbers | T1 |
| T3 | Coverage gates, provoked | T2 |
| T4 | `pip-audit` + `npm audit` in CI, provoked | T1 |
| T5 | CSP report-only, both tiers | T1 |
| T6 | Security header sweep | T5 |
| T7 | Load-test baseline, recorded | T1 |
| T8 | Abuse cases, ADR-023, close-out | all |

---

## 6. Not in M12

- **No Playwright journeys.** ADR-020 §2's frontend-ownership question is
  unanswered and the UI is auth pages plus one lesson page. Journeys over that
  would be the inert control in a new costume. The `webapp-testing` skill is
  installed and ready for the day it is answered.
- **No CSP enforcement**, only report-only. Enforcing needs a report period
  first, and there is no deployment to collect reports from until M13.
- **No Renovate, no CodeQL.** Repository configuration, not code.
- **No invented performance thresholds.** §3.4.
- **No coverage gate on permissions or services.** §3.1.
