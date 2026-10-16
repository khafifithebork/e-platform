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

> **Amended at T4: `pip-audit` cannot do this, and the decision above was made
> without checking.** There is no `--severity` flag. The tool fails on any
> known advisory, and the only escape is `--ignore-vuln ID` per advisory.
>
> So the two tiers are asymmetric, and the asymmetry has a reason rather than
> being an oversight. `npm audit --audit-level=high` is exactly what §8.4
> specifies, and npm advisories carry a severity, so filtering *classifies*.
> OSV entries behind `pip-audit` frequently carry no CVSS at all, so filtering
> there would **discard what it cannot classify** — a gate that silently
> passes the unclassified is worse than one that is occasionally noisy.
>
> The backend gate is therefore stricter than what was approved. That is a
> real change in how often the build can fail, and it is recorded here rather
> than left to be discovered. `--ignore-vuln GHSA-...` with a comment naming
> who triaged it is the intended release valve: deliberately more awkward than
> raising a threshold, because raising a threshold is how a gate quietly stops
> covering anything.
>
> Both were provoked. A vulnerable pin makes `pip-audit` exit 1 and a clean
> tree exits 0; `npm audit --audit-level=high` exits 1 on a high advisory while
> `--audit-level=critical` exits 0 on the same one, which is what proves the
> threshold filters rather than being ignored.
>
> **Amended again after CI.** `--strict` had to go, and its absence does not
> soften the vulnerability gate: it governs *dependency collection* failures
> only, and a found advisory exits 1 either way — verified against a
> known-vulnerable pin both with and without it.
>
> What forced it: `pip install ".[dev]"` registers this project as a
> distribution, and the audit then tries to resolve
> `language-platform-backend 0.0.0` on PyPI, where it will never be. CI now
> installs editable and passes `--skip-editable`, which excludes exactly one
> package — this one. `--strict` cannot coexist with that, because it fails on
> *any* skipped dependency including the one `--skip-editable` was told to
> skip.
>
> This passed locally and failed in CI because the local virtualenv had never
> had the project installed into it at all. The verification environment
> differed from the one that matters, which is the same mistake as measuring a
> header on a 400 page (ADR-023 §5) — in a third costume.

**Provoked, not trusted.** A clean audit and a broken audit both print nothing
useful. The check is run against a deliberately vulnerable pin before it is
believed — ADR-006, applied to CI configuration rather than application code.

### Where the audits run — amended 2026-10-03

**Both audits now run as their own jobs, `audit-backend` and `audit-frontend`.**
Nothing above this line changes: same commands, same thresholds, the same
asymmetry for the same reason, `--skip-editable` on the same editable install,
and no `continue-on-error`. A failing audit still fails the pull request, and both
jobs are in `deploy-staging`'s `needs`, so it still blocks a deploy.

**What forced it.** §3 reasoned carefully about *how strict* the gate should be
and not at all about *where it sits*. As steps, both audits ran early in jobs that
do other work — and GitHub stops a job at its first failing step. On 2026-10-03
`braces` (GHSA-vfj7-8cjw-p6xm, high) turned out to be affected at `*`, every
published version, reachable only through `eslint-config-next`. The frontend audit
went permanently red, and the eleven steps behind it — type check, lint, 649
tests, the build, and all four `verify:*` scripts, including a budget gate added
in the same pull request — were reported **skipped**. CI could not say whether any
change on any branch was correct, for as long as the advisory stood.

**This is a failure of gate design, not of the threshold.** §3's stated enemy is a
gate that gets disabled during a deadline. An audit ordered ahead of every other
check is a *more* tempting thing to disable than a noisy one, because disabling it
is the only way to learn whether the code works. The ordering was quietly working
against the decision it was implementing.

**What was nearly lost in the fix.** The obvious version of this change leaves
`deploy-staging`'s `needs` alone, which would have removed the audit from the
deploy gate entirely — a security control deleted by a change whose purpose was to
strengthen a signal. `test_staging_needs_both_test_jobs` asserted an exact set and
failed, which is the only reason it was noticed. Two further guards were added:
one that no audit command returns to a job that does other work, and one that
neither audit *job* is marked `continue-on-error` — a hole that did not exist while
they were steps, since one line at job level now turns the gate green and touches
nothing else.

**The threshold decision stands untouched, deliberately.** `braces` is a
dev-only transitive dependency whose only npm remedy is a two-major downgrade of
`eslint-config-next`. The recorded decision is to wait for upstream rather than
reach for `--omit=dev`, which would retroactively have hidden the `undici` chain
and `fast-uri` as well. The advisory still shows red. It just no longer blinds
everything else.

### Path-scoped frontend exceptions — approved 2026-10-08

The owner approved a repository-owned filter over `npm audit --json`, rather
than another dependency. The scanner and high/critical threshold stay the same.
`frontend/scripts/assert-dependency-audit.mjs` rejects command failures, malformed
reports, missing advisory causes, inconsistent counts, and unknown report formats.
The backend audit remains unchanged; its advisory-wide exception mechanism and
the frontend's narrower path mechanism are deliberately asymmetric.

Exceptions in `frontend/audit-allowlist.json` require an advisory ID, exact package
path, named triager, reason, and review deadline. Expired entries fail; stale entries
are printed for removal. Accepted exceptions are also printed, including their
reason and owner. The first entry expires after 2026-11-07 and covers only
`eslint-config-next>@next/eslint-plugin-next>fast-glob>micromatch>braces` for
GHSA-vfj7-8cjw-p6xm. This records accepted risk, not a claim of non-exploitability.

**An audit cause graph is insufficient to enforce a path exception.** npm groups
findings by package and may omit unaffected parents. The filter therefore resolves
all paths to the reported installed nodes from lockfile v3, including installed
optional and peer dependencies. Every matching path must start at a dev-only root
and contain only dev-marked nodes. Another path remains a failure, even when npm
does not name its parent in the audit report. Unsupported links, unresolved paths,
cycles, and excessive traversal fail rather than allowing an uncertain exception.

The October 8 recorded fixture contains four direct advisories (eleven affected
packages), not only the five-package braces chain seen on October 4. The live run
accepts that chain and **still fails** on proxy-addr (critical), sharp (high), and
source-map-js (high). Their remediation is separate work; none is excepted here.
`npm view braces version` still returned 3.0.3 on October 8.

The audit job runs the filter's regression tests before the live scan. Both audit
jobs remain deployment prerequisites; no `--omit=dev` or error suppression was added.
Tests use the recorded response and altered copies to exercise alternate paths,
runtime use, expiry, stale entries, corrupted output, and inconsistent process exit
codes. Removing the dev-only condition was verified to fail two tests.

### Frontend audit remediation — approved 2026-10-15

The owner approved applying the existing path policy to PR #110 and patching the
three remaining advisories. The lockfile now resolves proxy-addr 2.0.8
([advisory](https://github.com/advisories/GHSA-jqcg-44mw-7w3h)), source-map-js 1.2.2
([advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)) and sharp 0.35.5
([advisory](https://github.com/advisories/GHSA-wq5f-xc86-pv6w)). Wrangler's existing
direct pin advances from 4.144.0 to 4.151.0; its Miniflare 5.20261012.0-beta
dependency pins sharp 0.35.5, also compatible with Next's existing ^0.35.4 range.
The rest are compatible transitive patches. No new direct dependency or forced
audit-fix operation is introduced.

The raw npm report still lists the five-package braces chain. On October 15 the
registry still offered braces 3.0.3 and the
[advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) listed no patched
version. Only the previously approved development-only path is accepted, with
its original November 7 review deadline. This is not a zero-vulnerability claim.
New high/critical advisories, another path, runtime use, expired policy, malformed
output or scanner failure still fail the gate. Deployment prerequisites and the
backend audit are unchanged.

Verification records remain in STATUS.md and the current PR #110 checks. The
recorded October 8 fixture is retained unchanged so the tests continue proving
that unpatched proxy-addr, sharp and source-map-js findings cannot be excepted by
the braces policy.

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
