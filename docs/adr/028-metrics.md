# ADR-028 — Metrics: a token, no dependency, and a fourth number nobody can compute

**Status:** accepted
**Date:** 2026-08-30
**Decides:** M14 T6's fork, and one of ADR-027's two open questions
**Depends on:** architecture.md §3.7, ADR-006 (provoke every control),
ADR-009 (measure, do not reason about queries), ADR-027 (error reporting)

---

## Decision

**A `/metrics` endpoint in Prometheus exposition format, behind a bearer token,
answering 404 until one is configured.** No new dependency and no new account.

Plus the stuck-transcription alert §3.7 asks for, on the machinery M14 T4 built
and used once.

---

## 1. Why not Sentry Insights

T6's task line offers `/metrics` **or** Sentry Insights. Both looked blocked on
an account; only one really was.

Insights needs the Sentry account *and* tracing turned back on. M14 T5 set
`traces_sample_rate=0` deliberately — spans bill a quota separate from the 5k
errors, and ADR-027 §2 recorded that ceiling as unmeasured. **Choosing Insights
would compound the exact pressure T5 had just written down.**

`/metrics` needs a scraper, which is a service and a §5 gate — but *the endpoint
does not*. So the endpoint is built now and the scraper is a variable later.
Insights remains available and costs nothing to leave open.

---

## 2. No client library, and that is a real trade

The Prometheus text format is three lines per metric. We export gauges and
nothing else. A client library would arrive with a registry, a process
collector and a multiprocess mode this application has no use for, and would be
a §5 dependency gate for roughly thirty lines of string formatting.

**What we give up**, stated so nobody has to rediscover it: histograms and
summaries, `_total` counter semantics, and label handling. If a future metric
needs a histogram — request latency, most likely — that is the moment to
reconsider, and it is a small change because `render` is one function.

---

## 3. The token, and what an open `/metrics` would publish

**Empty token means 404.** Not 403, and not an open endpoint: the feature is
off, and there is genuinely nothing there. That is this repository's state,
because nothing scrapes it yet.

An unauthenticated `/metrics` publishes queue depth and backlog size — a
description of how loaded this system is and when it is weakest. That is not
catastrophic and it is not nothing, and it costs one environment variable to
avoid.

**404 unconfigured, 403 when the token is wrong**, and the difference is
deliberate. A wrong token means the endpoint exists and the caller got it
wrong, which is precisely the fact an operator needs when a scraper goes quiet.
Hiding it would only hide the endpoint from somebody who already knows the
path. ADR-019 §5 settled the same question for the admin site the same way:
refuse clearly rather than pretend.

**A plain Django view, not DRF**, and `healthz` learned why the hard way — DRF
defaults to `IsAuthenticated` here, so a scraper would get 403 forever, and it
throttles anonymous requests at 60/min per IP, which a 15-second scrape trips.
Both failures look like the endpoint working.

### 3.1 The one control no behavioural test can catch

Replacing `secrets.compare_digest` with `==` changes nothing observable: same
statuses, same bodies, every other test green. What changes is that the token
leaks its prefix to anyone who can measure a few thousand requests.

It is asserted from the **syntax tree** instead, with a twin that catches an
`==` left behind beside a `compare_digest` added elsewhere. This is the third
time this repository has needed a structural assertion for a property no
behaviour exposes, after M4's resolver-duplication guard and M14 T5's vendor
seam.

---

## 4. Three rules about what a metric may say

Each is a failure rather than a preference.

1. **Unreadable is absent, never an error.** Queue depth needs Redis, and an
   endpoint that 500s because the thing it monitors is down is worthless
   exactly when it is needed. A gap is visible in a dashboard; a failed scrape
   reads as "monitoring is broken". Provoked against an address nothing
   answers, so the real path runs — including the one-second timeout, which is
   why the scrape returns at all.

2. **No labels, therefore no identifiers.** A course slug or subscription id in
   a label is personal or commercial data on a surface something outside this
   system scrapes and retains. Asserted structurally: no metric may carry a
   label at all, which removes the route rather than policing it.

3. **Read-only**, asserted rather than claimed.

**Age is exported beside every count**, because they fail differently. One
unprocessed webhook from four days ago is a broken handler; fifty from the last
minute is a busy worker, and a count alone shows the same number for both.

`FAILED` transcripts are excluded from "unfinished" deliberately: a failed
transcription has a status somebody can act on, and counting it would make the
metric climb forever after one permanent failure and train whoever reads it to
ignore the number.

---

## 5. The fourth metric, which cannot be computed

**architecture.md §3.7 lists four metrics. T6's task line carries three.** The
missing one is **"video minutes delivered"**.

Dropping it is correct and is recorded here rather than inherited silently. It
is a *provider-reported billing* figure; no video provider has been chosen —
M5 ships a fake behind the adapter (ADR-012 §1) — and computing it from our own
data would be inventing a provider capability, which CLAUDE.md §6 forbids by
name.

**It is also the only one of the four that is about money**, so it must come
back with the Mux decision rather than vanish with this note. Whoever integrates
a real video provider owns it.

---

## 6. One of ADR-027's two open questions is answered; the other is not

**Answered — repeated-error volume against the 5k quota.** T6 was asked to look
at it. It has not been measured, and this ADR says so rather than guessing:
measuring it needs a DSN and a real error loop, neither of which exists.

What is now true is that the *symptom* has a number attached. `/metrics`
exports queue depth and both backlogs, so a task retrying in a loop — the most
likely source of repeated errors here — shows up as a rising queue depth on a
dashboard before it shows up as an exhausted Sentry quota. That is not the
measurement ADR-027 asked for, and it is a cheaper early warning than the one
it was worried about.

**Not answered — whether to close the Cloudflare Worker gap** with
`@sentry/cloudflare` (ADR-027 §4). It is another dependency and another §5
gate, and T6 did not touch it. **It remains open and unowned.**

---

## 7. What has never happened

**Nothing scrapes this endpoint**, because there is no scraper. `/metrics`
answers 404 in every environment today.

What *is* proven, against the running stack rather than asserted: an
eleven-day-old transcript was injected into the dev database, `report_metrics`
reported it, the alert task ran, and a real message arrived in Mailpit reading
*"Transcription backlog: 1 unfinished, oldest 11 days"* — with the course title,
lesson title, instructor address, slug and transcript id all confirmed absent.
Queue depth read from the live Redis broker on the same run.

So the numbers and the alert are demonstrated. The *scraping* is not, and
choosing a scraper is the §5 decision this ADR deliberately leaves for whoever
provisions.
