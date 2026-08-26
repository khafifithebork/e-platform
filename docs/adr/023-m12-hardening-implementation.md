# ADR-023 — M12 hardening: what implementation settled

**Status:** Accepted
**Date:** 2026-08-26
**Spec:** `docs/specs/m12-hardening.md`
**Decisions before code:** `docs/adr/022-m12-hardening-decisions.md`

---

## 1. The milestone's premise was wrong, and that was the finding

M12 was specified as maintenance: *close coverage gaps, tighten CSP, dependency
audit clean*. Three of those words turned out to be false.

- **"Close coverage gaps."** There were none. Every §8.1 target was already met
  — permissions 100% against a ~95% target, services 97.5% against ~85%. They
  had never been *measured*, which is a different thing and is why the task
  existed.
- **"CSP tightened."** There was no CSP anywhere.
- **"Dependency audit clean."** No audit ran. CI had two jobs and neither
  audited anything.

ADR-019 §1 and ADR-021 §1 each found one control that a document described and
nobody built. M12 found two more in a single milestone. **Three milestones,
four instances. This is not a run of bad luck; it is the default.**

The rule ADR-022 §1 proposes and this ADR confirms: **when a milestone's
objectives use maintenance verbs — tighten, close, clean up — check whether the
thing exists before planning the work.** The plan for M12 would otherwise have
been four small tasks, and two of them would have been discovered mid-flight.

---

## 2. What the coverage numbers were actually good for

The measurement itself was uneventful. The 74 uncovered statements were the
useful half, and three of them shared one shape:

**A check written as a backstop, tested only through the path that makes it
unreachable.** `grant_access_override` refuses a bad duration and a blank
reason, and both refusals had tests — through the API, where the serializer
rejects first, so the service's own guards never executed. Their own comment
says they exist "because the service is reachable from a management command
where no serializer runs", and nothing called it that way.

That is not a statistic. It is a control that survives deletion with a green
suite, and the deletion surfaces the first time somebody grants an override
from a shell.

`accounts/axes.py` had the same shape: its form-field fallback exists because
Django Admin posts a form, and every test in the suite posts JSON — so the half
that gives the brute-force lockout something to key on was the uncovered line.

**Coverage as a percentage said everything was fine. Coverage as a list of
lines said where to look.**

---

## 3. 100% branch coverage does not mean every test is load-bearing

Provoking the resolver gate by deleting a test **did not work**: coverage stayed
at 100%, because other tests covered the same branches. The gate only fired
when genuinely uncovered code was added.

Both facts are worth keeping. The gate works — 96.21%, build fails, re-verified
after eight milestones. And "100% branch coverage" is not a claim that the test
suite is minimal or that any particular test is necessary. It is a claim about
the code, not about the tests.

---

## 4. `pip-audit` cannot do what ADR-022 §3 decided

Recorded in full as an amendment inside ADR-022 §3. The short version: there is
no `--severity` flag. "Fail on high and critical only" is implementable for
`npm audit` and not for Python, and it was approved without checking.

The asymmetry that replaced it has a reason rather than being an oversight. npm
advisories carry a severity, so filtering *classifies*; OSV entries behind
`pip-audit` frequently carry no CVSS, so filtering there would **discard what it
cannot classify**. A gate that silently passes the unclassified is worse than
one that is occasionally noisy.

**The backend gate is therefore stricter than what was approved**, which is a
real change in how often the build can fail.

---

## 5. Two provocations lied before they told the truth

**`pip-audit | tail` reported exit 0 against a vulnerable pin.** That was
`tail`'s exit code. The tool was working perfectly and the measurement was
worthless — and a gate reported as "verified exit 0" is a gate nobody would
look at again.

**A header probe run outside pytest measured a 400 page.** It tripped
`DisallowedHost`, and the missing `X-Frame-Options` it reported was the header
set of Django's error response, not of the endpoint. It was caught only because
the result contradicted a test that was already passing.

Both belong to the same family as M11's misfired `.replace()`: **the
provocation is code too, and an incorrect provocation is indistinguishable from
a working control.** The habit that catches it is asserting something about the
provocation itself — that the edit applied, that the exit code came from the
right process, that the response was the one intended.

---

## 6. The load test's only check is a status code

`infra/load/catalogue.js` asserts no latency threshold and one status code, and
the first run is why: it reported a tidy 532ms p50 with **100% of checks
failing** on `DisallowedHost` 400s.

A load test where every request errors reports excellent latency. The status
check is not a formality around the real measurement; it is what makes the real
measurement mean anything.

**The recorded baseline is explicitly not a production number.** It ran against
the dev image with `DEBUG=True`, where Django retains every executed query for
the life of the request. `BASELINE.md` leads with that, because the failure mode
for that file is somebody quoting 419ms as a production figure a year from now.

What it did confirm: **search is the most expensive endpoint**, by ~20% at p50
and ~30% at p95 — the ordering M11 asserted when it gave search its own throttle
scope, now measured.

---

## 7. Disabling throttling to measure it, without a production footgun

A load test runs from one host against a per-IP limit, so with throttling on
every run reports the limit rather than the endpoint.

**The switch lives in `config/settings/local.py` and nowhere else.** Production
never loads that module, so a way to disable throttling cannot exist there by
construction — which is a stronger guarantee than a flag in `base.py` that
production is expected to override.

That claim is a test rather than a comment, including a structural one asserting
`local.py` is the only settings module that mentions the variable. Moving the
read into `base.py` fails three tests.

This is the one piece of M12 worth a second opinion: a flag that disables a
security control is still a flag that disables a security control, even when it
cannot reach production.

---

## 8. Abuse case 1 is partly unmet, and says so

The case asks that a breaking CSP directive be caught "by a report-only period
with somewhere to send reports". The policy is report-only. **There is nowhere
to send reports** — `report-uri` is read from the environment and omitted when
unset, because inventing an endpoint would put a fabricated URL in the header
of every response.

What replaced it locally is stronger than nothing and weaker than a report
period: the tests **inspect the markup the admin actually sends** and ask
whether the policy would permit it. That found the answer M13 needs — Django's
admin index ships **no executable inline scripts and no inline event
handlers**, so the strict policy looks enforceable.

M13 owns the report endpoint and the decision to enforce.

---

## 9. Carried out of M12

- **The frontend still has no owner** (ADR-020 §2). M12 dropped the Playwright
  journeys for it. **Third milestone in a row.** The `webapp-testing` skill is
  installed and the tooling question is settled; what is missing is a product to
  walk through.
- **CSP is report-only and unenforced.** M13 collects reports and decides.
- **`CREATE EXTENSION pg_trgm` is verified locally, not on Neon.** It ran
  against a live Postgres for the first time in T7, as superuser `app`. A
  managed provider may not grant it. M13.
- **The load baseline is dev-shaped.** M13 measures production.
- **No Renovate, no CodeQL**, by decision. M13.
