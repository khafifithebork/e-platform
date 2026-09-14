# Provisioning — the lean tier

What to create, in what order, what each thing costs, and what the cheap
version gives up.

`deploying.md` covers what happens on a merge. This covers what must exist
before that first merge means anything.

**Assumption:** the budget target is roughly **$5/month**, not $44. ADR-025's
hosting decision is unchanged — same three providers, same shapes — this is the
same architecture on free tiers with a smaller box. Nothing here needs a code
change.

---

## 1. The bill, and why it is not $44

ADR-002 §5 costs B-lite at $44/month. Two of those lines are for software that
does not exist in this repository.

| Line | ADR-002 | Lean | Why |
|---|---:|---:|---|
| Cloudflare Workers | $5 | **$0** | Free plan. Static asset requests are free and unlimited |
| Hetzner CX33 → CX22 | $10 | **~$5** | 2 vCPU / 4 GB at ~€4.35 |
| Neon Postgres | $15 | **$0** | Free plan |
| Cloudflare R2 | $0 | **$0** | 10 GB free, **egress free at any volume** |
| Mux video | $9 | **$0** | **Not integrated** — `providers/fake_video.py` is the only implementation |
| Deepgram | $5 | **$0** | **Not integrated** — `providers/fake.py` is the only implementation |
| Resend | $0 | **$0** | 3,000/month free |
| Sentry | $0 | **$0** | 5k errors/month free |
| **Total** | **$44** | **~$5** | plus a domain |

**The $14 for Mux and Deepgram is a forecast, not a bill.** M5 and M6 both
shipped against fakes deliberately (ADR-012 §1), so deploying what exists today
uses neither. They return when someone writes the adapter, and §4 below prices
that decision.

---

## 2. Component by component

Every free-tier figure below was read from the provider's pricing page. Anything
estimated is marked **[E]**; anything unverified is marked **⚠️**.

### 2.1 Domain and DNS — Cloudflare

The one thing no document in this repository has ever named. Everything else
depends on it: `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, the Worker route, the
API hostname, Resend's SPF and DKIM records.

**Do:** register or transfer the domain, put DNS on Cloudflare, decide two
hostnames — one for the web surface, one for the API.

**Cost:** registration only. DNS is free.

### 2.2 Frontend — Cloudflare Workers, free plan

| Free plan | |
|---|---|
| Requests | 100,000/day |
| CPU | **10 ms per invocation** |
| Static assets | **Free and unlimited** — they do not count against requests |
| Service bindings | Available (the `WORKER_SELF_REFERENCE` binding works) |

**The free tier suits this application unusually well, and by accident.**
Invariant 15 makes the public catalogue statically generated, and Cloudflare
bills static asset requests at nothing. The marketing surface is free *because*
of a decision ADR-024 made for reliability.

**⚠️ The 10 ms CPU limit is the risk.** Two things consume it:

- **The one dynamic route** — `/courses/[slug]/lessons/[lessonSlug]` — does
  React SSR on every request.
- **Every `/api/*` call**, because `next.config.ts` rewrites them through the
  Worker to Django.

Test both before committing. The second has a fix that costs nothing — see §5.

### 2.3 App tier — Hetzner CX22 with Dokploy

Runs Django (ASGI, invariant 12), Celery, Beat at exactly one replica
(ADR-001 §2.2), Redis, and Caddy. `infra/hetzner/compose.yaml` is written.

**This is the only line that cannot be free.** Celery, Beat and Redis need an
always-on process, and free compute tiers sleep. A sleeping worker means
scheduled tasks silently do not run, which is worse than not having them.

| | CX33 (ADR-002) | CX22 (lean) |
|---|---|---|
| vCPU / RAM | 2 / 8 GB | 2 / **4 GB** |
| Price | €8.49 | ~€4.35 |

**⚠️ The 4 GB is not verified.** ADR-002 says CX33 runs the stack "comfortably
at Scenario 1–2"; halving RAM is a judgement, not a measurement. Hetzner resizes
in place, so the recovery is a reboot rather than a migration. Watch memory
after the first real traffic.

**Region: Falkenstein or Nuremberg** — architecture.md §3 wants EU, and learners
are EU and MENA.

### 2.4 Database — Neon, free plan

| Free plan | |
|---|---|
| Storage | **0.5 GB per project** |
| Compute | 100 CU-hours/project |
| Branches | 10 |
| Autosuspend | after 5 min |
| **History retention** | **6 hours** |

**Three consequences, one of them serious.**

**⚠️ Six hours of history is not a backup.** M14 T8 specifies Neon PITR *and* a
weekly `pg_dump` to R2, on the reasoning that "a backup in the same account as
the database is not a backup". On the free plan **the pg_dump stops being the
second copy and becomes the only real one.** T8 gets more important here, not
less, and T9's restore drill goes from prudent to necessary.

**0.5 GB is a ceiling you will reach.** `deployment-strategy.md` estimates
1–2 GB at Scenario 1 **[E]**. A launch with an empty catalogue sits far below
it; a full 60-hour catalogue with transcript segments will not. Watch it, and
treat crossing it as the trigger in §6.

**Autosuspend costs the first visitor a cold start** after five idle minutes.
On a site with no traffic yet, that is most visitors.

**Branches are free and there are ten.** M13 T8 wants a staging branch; that
still works.

### 2.5 Object storage — Cloudflare R2

| Free tier | |
|---|---|
| Storage | 10 GB-month |
| Class A ops (writes) | 1 million/month |
| Class B ops (reads) | 10 million/month |
| **Egress** | **Free. At any volume.** |
| Paid storage | $0.015/GB-month |

**Egress being free is the single most important number in this document**, and
§4 is where it pays.

R2 holds the masters (invariant 7). Uploads go browser → R2 by presigned PUT
(invariant 6), so they never touch Django and never consume the app tier's
bandwidth.

### 2.6 Email — Resend, free plan

3,000 emails/month, **100/day**, 3 domains.

`deployment-strategy.md` estimates ~2,000/month at Scenario 1 **[E]**, which
averages 67/day and fits. **The daily cap is the one to watch**, because our
sends are bursty rather than smooth — a batch of notifications can exceed a day's
allowance while the monthly figure looks comfortable.

**Do:** verify the sending domain (SPF + DKIM). Skipping this is how transactional
mail silently lands in spam, and nothing in the application can detect it.

### 2.7 Errors — Sentry, Developer plan

5,000 errors/month across **all** services, one user, 30-day retention. There is
no spend cap on this tier; the quota is the cap (ADR-027 §2).

Already built (M14 T5). Set `SENTRY_DSN` and it starts working; leave it empty
and nothing initialises. **Give each service its own project**, because separate
DSNs are the only way to mute one noisy tier without muting all three.

### 2.8 Uptime monitoring

**⚠️ Not `/healthz` alone.** M13 T10's rollback rehearsal measured `/healthz`
returning 200 while every catalogue page returned 500 — that endpoint is a
liveness probe and touches no database, by design. A monitor pointed only there
would have reported the site healthy throughout an outage.

Point it at a page that exercises a real read. The public catalogue is
unauthenticated and is what a visitor actually meets.

Free tiers exist (UptimeRobot, Better Stack). Choosing one is a §5 gate.

### 2.9 Metrics

`/metrics` exists (M14 T6), token-gated, and answers 404 until `METRICS_TOKEN`
is set. **Nothing needs to scrape it on day one** — `python manage.py
report_metrics` gives the same numbers to a person, and `--prometheus` prints
exactly what the endpoint serves.

Add a scraper when there is something to watch. It is a §5 gate.

---

## 3. Provisioning order

Dependencies, not preference.

1. **Domain** → Cloudflare DNS
2. **Cloudflare account** → `wrangler login`, create the R2 bucket
3. **Neon project**, EU region → both connection strings, then a staging branch
4. **`check_database` against staging** — one command; closes M12's `pg_trgm` handover
5. **Hetzner CX22**, Falkenstein/Nuremberg → Dokploy → point at `infra/hetzner/compose.yaml`
6. **DNS records** → API hostname at the box, web hostname at the Worker
7. **Resend** → verify the domain, SPF and DKIM
8. **The `wrangler dev` cookie check** — closes ADR-025's last unknown
9. **GitHub → Environments → production → Required reviewers**
10. **Then** set `DEPLOY_ENABLED=true`

**Step 9 before step 10.** Without it the first merge deploys to production
unattended, and the approval this pipeline claims to have is a claim it cannot
keep.

### 3.1 One environment, not two

The pipeline deploys staging then production with different origins and Worker
names. **One VPS means one environment.** Neon's free branches cover the
database half, but the app tier does not split.

Two ways out, and this is a decision rather than a detail:

- **Production only.** Point both jobs at the same place, or drop the staging
  job. Costs nothing; loses the property that the thing being approved has
  already run somewhere.
- **A second CX22** at ~€4.35. Restores it for the price of the first box.

---

## 4. Large video — four options, none of them integrated

**No video provider exists in this codebase.** `MediaAsset` carries `provider`
and `provider_asset_id`, M5's adapter interface is written, and `fake_video.py`
is the only implementation. So this is a decision with a cost, not a bill you
already have.

Sizes below assume a master at ~50 MB/min and delivery at ~20 MB/min **[E]** —
`deployment-strategy.md`'s blended figure. A 60-hour catalogue is 3,600 minutes.

| Option | Storage/mo | Delivery at S1 | Total | What you give up |
|---|---:|---:|---:|---|
| **A — no video yet** | $0 | $0 | **$0** | Video. Audio lessons still work |
| **B — R2 direct** | ~$2.70 | **$0** | **~$3** | Adaptive bitrate, HLS, per-title encoding |
| **C — Mux** | — | — | **~$9** | Nothing. 100k delivered min/month free |
| **D — Bunny volume** | — | — | **~$3** | PoP selection work; bitrate/region risk |

C and D come from ADR-002 §4.1's verified table; A and B are new here.

### 4.1 Option B is new, and it is a real option

**R2 egress is free at any volume.** 10,000 delivered minutes/month at 20 MB/min
is 200 GB — and it costs nothing. Only storage bills: 180 GB of masters at
$0.015 = **~$2.70/month**.

It fits the invariants without bending them. A presigned R2 `GET` is
"browser → CDN via a signed token" (invariant 6). An `r2` provider adapter
minting those satisfies invariant 4, and stores `provider` + object key rather
than a URL (invariant 7).

**What it actually costs is quality, and the cost is not small.** Serving one
progressive MP4 means no adaptive bitrate: a learner on a weak mobile connection
gets buffering rather than a lower rendition, and there is no 720p cap doing
work for you. **Our learners are EU and MENA, substantially on mobile**, which is
exactly the population adaptive bitrate exists for.

So: **a defensible way to launch, not a place to stay.**

### 4.2 What I would do

**Launch on A or B and decide later.** Neither forecloses anything — every option
is one adapter behind invariant 4, which is the entire reason M5 built it that
way.

**When video budget appears, Mux at ~$9 is the honest default**: 100,000
delivered minutes a month are free, basic-quality encoding costs nothing, and it
needs no engineering beyond the adapter. Bunny is 5–10× cheaper at Scenario 3
and carries PoP and bitrate work that is not worth it at Scenario 1.

**And ship the audio-mode toggle whichever you pick.** ADR-002 §7 measured Mux
billing audio-only assets at **one tenth** the 720p rate. Language learning works
audio-only — commuting, revision — so it is a product improvement that happens to
cut delivery cost by up to 90%.

### 4.3 Transcription

Same shape. `providers/fake.py` is the only implementation, and
`deployment-strategy.md` establishes that transcription is a **one-off cost per
asset, not recurring** — the whole Scenario 3 catalogue costs under $160 **[E]**.

So it is not a monthly line at all. It is a bill that arrives when you add
catalogue, and it can wait.

---

## 5. One change that saves quota and answers an open question

`/api/*` currently routes through the Worker via Next rewrites, so **every API
call burns free-tier requests and CPU**. A Cloudflare Origin Rule sending
`/api/*` straight to Django bypasses the Worker entirely.

That is **CLAUDE.md §11 #4** — BFF versus path routing — open since M13, and
ADR-001 §2.1 already sequenced it as "Next rewrites now, a Cloudflare Worker
before launch". A tight budget turns it from a preference into a lever.

---

## 6. When to leave the lean tier

Triggers, so the decision is made by a number rather than by an incident.

| Signal | Move |
|---|---|
| Neon storage nears 0.5 GB | Neon Launch — usage-billed, and it restores 7-day PITR |
| Worker CPU errors on the lesson route | Workers Paid, $5 |
| Resend hits 100/day | Resend Pro, $20 — or spread the sends |
| Memory pressure on the box | Resize to CX33 in place |
| Real video traffic | §4 — Mux, then Bunny at scale |
| A second person needs Sentry | Sentry Team (free tier is one user) |

**The lean tier is a starting configuration, not a permanent one.** Every line
upgrades independently and none requires a migration.

---

## 7. What this does not change

**The architecture is identical.** Same providers, same shapes, same
`compose.yaml`, same pipeline. ADR-025 stands; this is the same decision on
cheaper tiers.

**And the honest state, unchanged by any of it:** the deploy pipeline has never
run, no event has ever reached Sentry, nothing scrapes `/metrics`, and the
rollback runbook is half-rehearsed. Those are facts about the world, not about
the budget, and they stay true until somebody provisions.
