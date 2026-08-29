# ADR-027 — Error reporting: one seam, no spend cap, and half a Worker

**Status:** accepted
**Date:** 2026-08-29
**Decides:** M14 T5's three open questions
**Depends on:** ADR-002 §5 (Sentry budgeted at $0), ADR-006 (provoke every
control), ADR-023 §1 (a documented control is not a control), ADR-025 (B-lite)

---

## Decision

Sentry across Django, Celery and the browser. Configured entirely from the
environment, inert without a DSN, with the vendor SDK imported in exactly one
module per tier.

**The server-side Next.js half is not delivered.** It is built, it is correct,
and it does not reach the Cloudflare Worker. §4 has the measurements.

---

## 1. Sentry is not an adapter, and invariant 4 is still kept

Invariant 4 puts every external provider behind an adapter in
`<app>/providers/`. Sentry was put in `apps/core/observability.py` instead.

**An adapter exists so a vendor can be swapped at a call site. Sentry has no
call site.** It installs itself into the interpreter at boot — into Django's
middleware stack, Celery's signals, the logging module — and our code never
invokes it. A `providers/sentry.py` wrapping a function that runs once would be
an abstraction over nothing, and the precedent is already on this side:
`django-axes`, `django-csp` and `django-otp` are all vendor integrations with
no adapter.

What the invariant protects is that the vendor can be removed or replaced by
editing one file, and that is kept and asserted:

| Tier | The one module | The guard |
|---|---|---|
| Backend | `apps/core/observability.py` | `test_exactly_one_module_imports_the_sdk` — parses every module under `apps/` and `config/` |
| Frontend | `src/lib/observability/sentry.ts` | `observability.test.ts` — same idea over `src/` and the root files |

The backend guard reads the **syntax tree**, not the text. Every previous
structural check in this repository has, at least once, matched its own
explanatory comment; a syntax tree contains no comments and cannot.

The frontend has a second reason for its seam. Next loads `instrumentation.ts`
and `instrumentation-client.ts` in different runtimes, and the obvious shape is
a `Sentry.init` in each. Two initialisations drift, and the half that drifts is
the browser — where the options that matter are the privacy ones.

---

## 2. The task asked for a spend cap that does not exist on this tier

M14's task line reads *"Sentry in Django, Celery and Next.js; DSN from env;
**spend cap**"*. Sentry's pricing page puts **"set maximum spend threshold" on
its paid plans only**. ADR-002 §5 budgets Sentry at $0, which is the Developer
plan:

| Developer plan | |
|---|---|
| Errors | **5k/month**, across every service |
| Users | One |
| Retention | 30-day lookback |
| Spend threshold | **Not available** |

**So there is no cap to configure, and the quota is the cap.** Recording that
matters more than it sounds: without it, a future reader holding the task list
goes looking for a setting that was never available and concludes somebody
forgot.

What replaces it is in code, because staying inside the quota is now a design
constraint rather than a billing control:

- **Tracing off** — `traces_sample_rate=0`, `tracesSampleRate: 0`. Tracing
  bills a *separate* quota, and whether we want it is T6's question.
- **A DSN per service.** Separate Sentry projects are the only way to mute one
  noisy tier without muting all of them.
- **The test suite cannot spend the budget.** `config/settings/test.py`
  overwrites `SENTRY_DSN` rather than defaulting it, because it reads
  `backend/.env` through `read_env` — a developer with a real DSN there would
  otherwise report every deliberately-raised exception in 1459 tests to a live
  project. One `make test` could spend a month.

**Still unresolved:** 5k errors a month is a real ceiling for a public site,
and nothing here throttles a loop that reports the same error repeatedly.
Sentry's own client-side rate limiting is what stands between us and a bad
afternoon, and it has not been measured. T6 should look at it.

---

## 3. Personal data, and what the vendor's scrubber does not do

`send_default_pii=False` in both tiers, explicitly rather than by default — a
default is a fact about a version, and an explicit line is one a test can
assert. With it off, no Django user object, no request body and no headers.

On top of that, both tiers redact anything shaped like an email address from
every event, by value.

**This complements the SDK's own scrubber rather than repeating it**, which was
checked against the installed package rather than assumed: that scrubber is
**key**-based — it removes values under names like `password` — and `email` is
not in its denylist. More to the point, no key-based scrubber can reach an
address inside an exception *message*, and that is the shape this codebase
produces: account and notification errors quote the address they were handed.

**The cap has a price and it is written down in the test.** Redaction stops
descending after ten levels, so an address buried deeper survives. The
alternative is a `RecursionError` inside `before_send`, which drops the event —
the one failure mode an error reporter must not have.

No Session Replay. It records the DOM, and the authenticated pages carry a
learner's name, their courses and their progress; recording that to a third
party is a different decision from reporting an error, and not one T5 is
making. Refused by a name filter rather than by omission, so a future SDK
default cannot turn it on.

---

## 4. The Next.js server half does not reach the Cloudflare Worker

**This is the finding, and it was measured rather than reasoned about.**

`instrumentation.ts` is correct. Under `next build` it compiles to
`.next/server/instrumentation.js` and the Sentry SDK lands in the server
chunks. Under OpenNext it does not survive into the Worker:

| Observation | Result |
|---|---|
| JS in `.open-next/server-functions/` referencing `@sentry` | **none** |
| Only Sentry JS anywhere in `.open-next/` | the **browser** asset chunk |
| Worker size with the server SDK added | 1061.49 → **1061.61 KiB** gzipped |
| Chunks the copied instrumentation stub requires | **not present beside it** |

A 0.12 KiB delta is the size of nothing. A bundled server SDK would be
hundreds.

**What was ruled out.** The file location is right — Next picked it up, which
the `.next/server/instrumentation.js` artifact proves. The Wrangler
preconditions Sentry names are met: `nodejs_compat` is set and the
compatibility date is `2026-08-29`, past the `2025-08-16` floor that exists to
provide `https.request`. And `withSentryConfig` is not the missing wiring: with
the plugin the server function still contained no Sentry, and the Worker grew
2.2 KiB.

That is two attempts at one fix, so per CLAUDE.md §9 this reports rather than
continues.

**What it costs.** Errors thrown in Server Components, route handlers and
server actions are reported by nothing. The blast radius is narrower than it
first appears — the `(marketing)` surface is statically generated, so its
failures are build failures and CI is loud about them (ADR-024), and the
learner pages are largely client components. The genuinely uncovered path is
the one dynamic route, `/courses/[slug]/lessons/[lessonSlug]`. **Django, where
the business logic lives, is fully covered by the backend half.**

**What is open.** The documented alternative is `@sentry/cloudflare` wrapping
the Worker entry point, which is another dependency, another §5 gate, and a
change to `open-next.config.ts`. It is a task, not a patch, and it belongs
wherever the owner decides — T6 is the natural home.

`instrumentation.ts` is **kept, not deleted.** It is correct, it is the
documented Next integration, it works in development where it is doing its job
today, and it starts working if the frontend ever runs on Node. Its docstring
says plainly where it does not run, because the alternative is the next reader
assuming production is covered.

---

## 5. A malformed DSN crashes rather than disables

A DSN typo could either take the process down or silently disable reporting.
**Silence is the worse failure:** it is exactly ADR-006's inert control, and it
would be discovered during the incident it was meant to report.

Crashing is caught where it is introduced — the deploy pipeline polls
`/healthz` before proceeding — so the blast radius is a failed deploy. This is
the SDK's own behaviour, pinned by a test so a future version that starts
swallowing bad DSNs is noticed here rather than in production.

---

## 6. What has never happened

**No event has ever reached Sentry from this codebase.** No DSN exists.

Everything above is configuration, refusal and scrubbing — all testable, none
of it delivery. This is ADR-006's inert control by construction rather than by
oversight, and it stays inert until somebody provisions the account. The first
thing to do when that happens:

1. Confirm an event arrives, from each tier, with its `request_id` tag.
2. Turn on source map upload — `withSentryConfig` becomes worth adding once an
   organisation, a project and an auth token exist. Until then stack traces
   from the browser are minified.
3. Decide §2's open question about repeated-error volume against the 5k quota.

---

## 7. Two things found in passing

**The dev API container died on the new dependency.** `ModuleNotFoundError: No
module named 'sentry_sdk'` — the compose stack mounts the source but carries
the image's site-packages, so adding a backend dependency requires a rebuild.
This is the **M12 T7 failure class** that M13 T5's release-image smoke check
was built to catch, reproduced by accident and behaving exactly as that task
predicted.

**`connect-src 'self'` would have silenced the browser SDK.** The CSP is
report-only, so the failure would have been invisible: Sentry appears to work
in development and reports nothing the moment M13 enforces. The ingest origin
is now *derived from the DSN* rather than configured separately, so the allowed
origin cannot disagree with the one being posted to.
