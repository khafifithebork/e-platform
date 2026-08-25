# ADR-022 — M12 hardening: four decisions, and two controls that were never built

**Status:** Accepted
**Date:** 2026-08-25
**Spec:** `docs/specs/m12-hardening.md`

---

## 1. Two documented controls did not exist

M12 was specified as "close coverage gaps; Playwright journeys; load test;
`check --deploy` clean; dependency audit clean; CSP tightened". Two of those
describe controls that were never built, and both read as maintenance work in
the document.

**There is no CSP.** Not in Django settings, not in middleware, not in
`next.config.*`. "Tightened" implies a policy exists to tighten. Introducing
one is a different task with a different risk: a wrong directive is either an
unprotected site or a blank page.

**No dependency audit runs.** architecture.md:848 specifies `pip-audit` and
`npm audit` in CI failing on high severity. CI has a `backend` job and a
`frontend` job and neither audits anything.

This is ADR-021 §1 and ADR-019 §1 for the third time: **a document describing a
control creates the impression of one, and the impression survives review
indefinitely, because the reviewer is reading the document that promised it.**
Three milestones have now found an instance. It is worth treating as the
default expectation rather than a surprise — when a milestone's objectives say
"tighten", "close" or "clean up", check first whether the thing exists.

**What was actually measured:** one coverage gate, on
`apps.entitlements.resolver`, at 100% branch. The §8.1 targets for permissions
and services have never been measured at all, so whether they are met is
unknown rather than assumed.

---

## 2. Gate only what §8.1 calls 100%

**Decision.** Measure every §8.1 area and report it. Fail the build only on the
100% targets.

**Why not gate the ~95% and ~85% areas.** A percentage target is a judgement
about *shape*, not a threshold. Coverage moves when code is deleted, when a
branch is simplified, when a serializer absorbs a conditional — none of which
are regressions. A gate that fails on those gets raised until it means nothing,
and a gate nobody trusts is worse than no gate because it also costs time.

**What replaces the gate.** The numbers go into the CI log and into STATUS, so
a drop is *visible* even though it is not fatal. Revisit once there is enough
history to say what a normal fluctuation looks like — which is a measurement,
not a guess.

**Billing webhooks and trial lifecycle are not deferred out of convenience.**
Neither exists: M8 and M9 own them and are both blocked. A gate on an empty
module reports 100% and guards nothing.

---

## 3. The audit fails on high and critical, and nothing softer

**Decision.** `pip-audit` as a dev dependency, `npm audit` from npm itself.
Both fail CI on **high and critical** severity only.

**Why not moderate.** A security gate that fires on things nobody will act on
this quarter is a gate that gets `|| true` appended within a month, usually
during an unrelated deadline. The failure mode to design against is not "we
missed a moderate advisory", it is "the audit was disabled and nobody
remembers".

**Provoked, not trusted.** A clean audit and a broken audit both print nothing
useful. The check is run against a deliberately vulnerable pin before it is
believed — ADR-006, applied to CI configuration rather than application code.

**Renovate and CodeQL are out of scope.** Both are repository configuration
rather than code, and CodeQL changes what runs on every push to a repository
this project does not yet pay for compute on. M13, with the rest of the
deployment surface.

---

## 4. CSP through `django-csp`, report-only, in both tiers

**Decision.** `django-csp` for the Django tier, `headers()` in
`next.config` for the Next.js tier. **Report-only first, in both.**

**Why a dependency rather than middleware we write.** CSP is unforgiving in a
specific way: the failure is silent. A missing directive does not raise, it
removes a stylesheet — and Django's admin uses inline styles, so a policy
without nonce support blanks the highest-value page in the system. Nonce
generation, report-only mode and per-view overrides are exactly the parts worth
not writing twice.

**Why both tiers rather than the edge.** Cloudflare rules would protect
production and nothing else, so a wrong directive is discovered by a user
rather than by CI. Next.js serves the product's HTML; Django serves the admin
site and DRF's browsable API, and M10 routed the admin precisely because it is
the higher-value target.

**Report-only is not a soft launch, it is the only honest first step.** There
is no deployment collecting reports until M13, so enforcement in M12 would be
enforcement nobody has observed. The report period belongs to M13, and this
milestone's deliverable is a policy that is *correct as far as anything can
tell locally* — including a test that the admin site still renders under it.

---

## 5. The load test records a baseline and invents no threshold

**Decision.** `k6`, scripted against the catalogue list, course detail and
**search**. The deliverable is p50, p95 and error rate at a stated concurrency
on stated hardware, written into STATUS. No pass/fail threshold.

**Why search is included when the objective names "catalogue and player".**
Search did not exist when that line was written. It is a ranked full-text query
over a GIN index and the most expensive thing an anonymous visitor can ask this
service to do — M11 gave it its own throttle scope for that reason. Load
testing the catalogue and omitting it would measure the cheap half.

**Why no threshold.** §6 forbids inventing infrastructure facts, and "p95 under
200ms" written today is exactly that: a number with no measurement behind it,
which a later milestone would either meet by accident or tune towards without
knowing whether it matters. A baseline with its conditions recorded is a fact.
A threshold derived from it later is a decision. The two must not be swapped.

**The player endpoint is not load tested.** It mints a signed token behind the
entitlement resolver, and load testing it means either bypassing the resolver —
measuring something the product does not do — or minting thousands of real
tokens. It arrives with a deployment that can be measured properly. M13.

---

## 6. What M12 does not do, and why it is not laziness

**No Playwright journeys.** ADR-020 §2's frontend-ownership question is still
unanswered, and the frontend is auth pages plus one lesson page. Journeys over
that surface would pass, prove nothing, and appear in a report as coverage —
which is the inert control in its most convincing costume yet, because the
milestone's own objectives name it.

The `webapp-testing` skill is installed and the tooling decision is made. What
is missing is a product to walk through, and that is a decision rather than a
task.
