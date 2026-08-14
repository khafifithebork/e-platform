# Deployment Strategy — Curated Language-Learning Subscription Platform

**Document type:** Infrastructure research, architecture comparison and recommendation
**Phase:** Research → Comparison → Architecture Selection → Cost Analysis → Recommendation
**Status:** Pre-implementation. No deployment steps or code included by design.
**Prepared:** August 2026
**Input analysed:** `Brainstormv1.md` — "Language Learning Platform — Feature Map, Strategy, and Progress" (v2.0)

---

## Evidence legend

Every material claim in this document is tagged so you can tell what is fact and what is judgement.

| Tag | Meaning |
|-----|---------|
| **[V]** | Verified against an official pricing page, official docs, or a primary vendor source. Link given. |
| **[E]** | Estimate — arithmetic built on [V] rates plus stated usage assumptions. |
| **[A]** | Assumption — a usage or product assumption I made because the brainstorm does not specify it. Challenge these first. |
| **[R]** | Engineering recommendation — my judgement, not a fact. |

Pricing was checked in August 2026. **Cloud pricing moves.** Hetzner raised cloud server prices by up to ~3.1× on some instance families on 15 June 2026 **[V]** ([Hetzner price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)) — a live reminder that no number below is permanent. Re-verify before committing budget.

---

# 1. Analysis of the Platform

## 1.1 What this product actually is

Stripping the brainstorm to its infrastructure-relevant shape:

- A **curated**, admin-approved catalogue — not an open marketplace. Content volume grows slowly and predictably.
- **One subscription tier, two billing intervals** (monthly/yearly), plus a trial state.
- **Video and audio lessons** with a player, progress tracking and resume.
- **App-generated transcripts and subtitles**, with a human review/approval workflow before publish.
- Three roles (student / instructor / admin) with a genuine **entitlement layer** gating content.
- Transactional email only at MVP. No community, no live classes, no native apps, no DRM, no instructor payouts.

Two features dominate every infrastructure decision:

1. **Video delivery.** The brainstorm names this Complexity Trap #1 and its own strategic guidance is to use hosted media services rather than build a pipeline. That guidance is correct, and this document quantifies why.
2. **Entitlement correctness.** Because access to *everything* is gated by subscription state, the boundary between your payment provider's webhooks and your database is the highest-risk surface in the system — higher than any hosting choice.

## 1.2 Requirement extraction

| Domain | MVP requirement | Near-term (Phase 2) | Future scale |
|---|---|---|---|
| **Frontend** | Server-rendered web app, mobile-friendly, fast catalogue + player pages. No native app. | Better player UX, interactive transcript | Possible native apps → API must stay clean |
| **Backend** | Single API/monolith. Auth, roles, entitlement checks, course CRUD, approval workflow, webhook receiver | Same, more endpoints | Stateless, horizontally replicated |
| **Database** | PostgreSQL. Relational, transactional. Users, subscriptions, entitlements, courses, lessons, progress, transcripts, audit log | Read replica for reporting | Replica + PITR + partitioned progress/event tables |
| **Auth** | Email/password + reset + verification. Sessions or JWT. Role-based authorization on every route | OAuth providers, 2FA for admin | SSO for B2B (§6.19 of brainstorm, post-MVP) |
| **Payments** | Hosted checkout, customer portal, webhook-driven subscription state, invoices, refunds, dunning | Plan switching, proration | Multi-currency, tax |
| **File storage** | S3-compatible object storage for PDFs, worksheets, images, subtitle files (VTT), instructor uploads | Storage quotas per instructor | Lifecycle policies, tiering |
| **Video** | Managed video platform: storage, transcoding, HLS/ABR, CDN, signed URLs | Multi-track audio, dual subtitles | Regional delivery tuning, possibly DRM |
| **Transcription** | Batch speech-to-text with word/segment timings → editable → published VTT | Translated subtitles | Higher volume, quality tooling |
| **Email** | Transactional only: verification, reset, trial start/ending, payment succeeded/failed, cancelled, expired | Lifecycle/retention emails | Separate marketing IP pool |
| **Background jobs** | Transcription pipeline (submit/poll/retry), trial-expiry sweeps, dunning, webhook retries, email sends | Digest emails, reporting rollups | Dedicated worker fleet, queue depth monitoring |
| **Caching** | Light. Rate limiting, session/entitlement cache, job queue backend | Catalogue page cache | Distributed cache, CDN page caching |
| **Search** | PostgreSQL full-text + trigram over a curated catalogue. Nothing more. | Filters, facets | Dedicated search engine only if catalogue >~2,000 items |
| **Analytics** | SQL queries over Postgres + privacy-friendly web analytics | Cohort/retention views | Event store or warehouse |
| **Monitoring** | Error tracking, uptime checks, logs | Structured logs, alerting | APM, tracing |

## 1.3 Traffic, storage and bandwidth model

The brainstorm gives no numbers, so these are my working assumptions. **Every cost estimate in this document depends on them — change them and re-run the arithmetic.**

| Variable | Scenario 1 (MVP) | Scenario 2 (Growing) | Scenario 3 (Established) | Tag |
|---|---|---|---|---|
| Registered users | 100 | 1,000 | 10,000 | given |
| Daily active users | 20 | 200 | ~2,000 | given |
| Catalogue size | 60 hours (3,600 min) | 200 hours (12,000 min) | 600 hours (36,000 min) | **[A]** |
| Avg watch per DAU per day | 15 min | 15 min | 15 min | **[A]** |
| **Video minutes delivered / month** | **~10,000** | **~100,000** | **~1,000,000** | **[E]** |
| Video bitrate served (blended) | ~2.7 Mbps ≈ 20 MB/min | same | same | **[A]** |
| **Video bandwidth / month** | ~0.2 TB | ~2 TB | ~20 TB | **[E]** |
| API requests / month | ~0.5 M | ~5 M | ~50 M | **[E]** |
| Database size | 1–2 GB | 5–10 GB | 30–60 GB | **[E]** |
| Object storage (non-video) | ~5 GB | ~25 GB | ~100 GB | **[E]** |
| Transactional emails / month | ~2,000 | ~15,000 | ~120,000 | **[E]** |

Three consequences fall straight out of this table:

- **Video is 60–85% of the infrastructure bill at every scale.** Compute and database are close to noise at MVP.
- **Transcription is a one-off cost per asset, not a recurring one.** It scales with *catalogue hours*, which a curated platform controls directly. At batch STT rates, transcribing the entire Scenario 3 catalogue costs under $160 **[E]** (§8.4). The expensive part of subtitles is human review time, not API spend.
- **API traffic is small.** Roughly 2,000 requests/minute at peak in Scenario 3 is comfortable for a single well-sized instance. You do not need exotic compute.

## 1.4 The one requirement the brainstorm does not mention: where the business is incorporated

This is not a hosting question but it changes the architecture, so it belongs here.

- Stripe supports merchants in a fixed list of countries — 46 as of 2026 **[V]** ([Stripe global](https://stripe.com/en-sg/global)) — and **Morocco is not among them** **[V]** ([independent analysis, May 2026](https://www.baas.ma/en/blog/stripe-maroc-2026-alternative)).
- Paddle, as a merchant of record, states it supports sellers and pays out worldwide excluding sanctioned countries **[V]** ([Paddle help centre](https://www.paddle.com/help/start/intro-to-paddle/which-countries-are-supported-by-paddle)).
- Polar is also an MoR but pays out via Stripe Connect Express, so its seller list is narrower than "global" **[V]** ([Polar docs](https://polar.sh/docs/merchant-of-record/supported-countries)).
- Lemon Squeezy still exists post-Stripe-acquisition and is being folded into Stripe Managed Payments **[V]** ([Lemon Squeezy, Jan 2026](https://www.lemonsqueezy.com/blog/2026-update)); treat it as in transition rather than a stable foundation for a new build. **[R]**

**Decision required before you write billing code** **[R]**: if the operating entity is Moroccan, plan for a **merchant of record** (Paddle is the safest fit on current evidence) or a licensed local PSP, not Stripe. If you incorporate in a Stripe-supported jurisdiction, Stripe Billing is the better developer experience. This choice determines your webhook schema, entitlement sync logic, refund flow and admin tooling — all of which the brainstorm treats as MVP-critical. Getting it wrong means rewriting §6.6, §6.7 and §6.8 of the feature map.

**MoR fees dwarf your infrastructure bill at MVP.** At roughly 5% + a fixed fee per transaction, 100 subscribers at $10/month costs about $100/month in payment fees — more than the entire Architecture B stack. **[E]** That is normal and acceptable; it just means "cheapest hosting" is the wrong thing to optimise first.

---

# 2. Deployment Options Researched

## 2.1 Video infrastructure (the decisive category)

| Provider | Model | Verified rates | Source |
|---|---|---|---|
| **Cloudflare Stream** | Per minute stored + per minute delivered. Encoding, ingest and egress free | $5 / 1,000 min stored (prepaid); $1 / 1,000 min delivered **[V]** | [CF Stream pricing](https://developers.cloudflare.com/stream/pricing) |
| **Mux Video** | Per minute encoded + stored + delivered, tiered by resolution | Basic quality: encoding **free**; 720p storage $0.0024/min-mo; 720p delivery $0.0008/min; **first 100,000 delivered min/month free**; audio-only billed at 1/10 the 720p rate; cold-storage discounts of 40% (30d unviewed) / 60% (90d unviewed) **[V]** | [Mux pricing docs](https://www.mux.com/docs/pricing.txt) |
| **Bunny Stream** | Per GB stored + per GB CDN delivered. Standard H.264 encoding free | Storage $0.01/GB-mo (first region); CDN standard network $0.010/GB EU+NA, **$0.060/GB Middle East & Africa**; volume network $0.005/GB flat to 500 TB; AI transcription $0.10 per language-minute; DRM $99/mo + per-license **[V]** | [Bunny Stream pricing](https://bunny.net/docs/stream/pricing) |
| **Cloudflare R2 + own pipeline** | Object storage, zero egress | $0.015/GB-mo Standard; Class A $4.50/M, Class B $0.36/M; egress $0; free tier 10 GB + 1M/10M ops **[V]** | [R2 pricing](https://developers.cloudflare.com/r2/pricing) |
| **Backblaze B2 + CDN** | Object storage, free egress to 3× stored | $6/TB-mo; free egress up to 3× average monthly storage, then $0.01/GB; unlimited free egress via CDN partners incl. Cloudflare and bunny.net **[V]** | [B2 pricing](https://www.backblaze.com/cloud-storage/pricing) |
| **Vimeo / Wistia** | Seat + plan based | Not competitive for API-driven course delivery at these volumes **[R]** | — |

Full cost modelling and the recommendation are in §8.

## 2.2 Application hosting

| Provider | Model | Verified rates | Source |
|---|---|---|---|
| **Hetzner Cloud** | Flat monthly VPS, large included traffic | Post-June-2026 EU prices excl. VAT/IPv4: CX23 €5.49, CX33 €8.49, CX43 €15.99, CX53 €29.49; ARM CAX11 €5.99 → CAX41 €40.99; dedicated-vCPU CCX13 €42.99 **[V]** | [Hetzner price list](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) |
| **Render** | Flat per-service + workspace fee | Starter web service $7/mo (512 MB, 0.5 CPU); Standard $25 (2 GB, 1 CPU); Pro Ultra $450; Postgres from $6/mo (Basic-256mb) + $0.30/GB-mo storage; Key Value (Redis) from $10/mo; bandwidth overage ~$0.15/GB; Pro workspace flat $25/mo with no per-seat fee since April 2026 **[V]** | [Render pricing](https://render.com/pricing), [analysis](https://checkthat.ai/brands/render/pricing) |
| **Railway** | Usage-metered per second | ~$10/GB-mo RAM, ~$20/vCPU-mo, $0.05/GB egress, volumes $0.15/GB-mo; Hobby $5/mo incl. $5 usage, Pro $20/seat incl. $20 usage **[V]** | [Railway pricing](https://railway.com/pricing) |
| **Vercel** | Seats + granular metering | Pro $20/seat/mo incl. $20 credit and 1 TB Fast Data Transfer, then $0.15/GB; Fast Origin Transfer $0.06/GB metered separately; Hobby is non-commercial and hard-capped at 100 GB **[V]** | [Vercel functions pricing](https://vercel.com/docs/functions/usage-and-pricing) |
| **Fly.io** | Per-machine metering, global regions | Good for multi-region latency; more moving parts than needed here **[R]** | — |
| **DigitalOcean** | Flat droplets + managed services | Managed Postgres from $15/mo single node; HA from $30 + matching $30 standby; read replicas from $15 **[V]** | [DO Postgres pricing](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/) |
| **AWS / GCP / Azure** | Everything, priced per dimension | Rejected for MVP: operational surface area and billing complexity are wildly disproportionate to a single-region monolith serving 20 DAU **[R]** |

## 2.3 Database

| Option | Verified rates | Notes | Source |
|---|---|---|---|
| **Neon** | Free: 0.5 GB storage, 100 CU-hours/project-mo. Launch $0.106/CU-hour, Scale $0.222/CU-hour, storage $0.35/GB-mo, no monthly minimum since Dec 2025 **[V]** | Real Postgres, branching, PITR, scale-to-zero. Always-on 0.25 CU ≈ $19/mo **[E]** | [pricing analysis](https://selfhost.dev/blog/neon-pricing-cost-of-serverless-postgres/), [comparison](https://www.bytebase.com/blog/postgres-hosting-options-pricing-comparison/) |
| **Supabase** | Pro $25/mo per org, includes 8 GB database, 100 GB file storage, $10 compute credit **[V]** | Bundles auth + storage + realtime. Good value *if you use the bundle*; partial lock-in if you use its Auth | [Neon vs Supabase](https://www.closefuture.io/blogs/neon-vs-supabase) |
| **DigitalOcean Managed PG** | $15/mo single node; $60.90 for 2 vCPU/4 GB; HA doubles it; daily backups, PITR, PgBouncer included **[V]** | Most predictable bill of the managed options | [DO docs](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/) |
| **Render Postgres** | From $6/mo; storage $0.30/GB-mo and **can only be increased, never decreased**; PITR gated behind higher tiers **[V]** | Convenient if the app is already on Render | [Render](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses) |
| **Self-hosted on VPS** | €0 marginal | Cheapest, and you own backups, restores, upgrades, failover. That is real unpaid work | — |

## 2.4 Supporting services

| Need | Option | Verified rates | Source |
|---|---|---|---|
| **Redis** | Upstash pay-as-you-go | Free 256 MB / 500K commands per month; then $0.20 per 100K commands, $0.25/GB-mo beyond first free GB; fixed plans from $10/mo **[V]** | [Upstash](https://upstash.com/pricing/redis) |
| | Self-hosted on the app VPS | €0 marginal; fine when the queue is small **[R]** | — |
| **Email** | Resend | 3,000/mo free; Pro $20/mo for 50,000 **[V]** | [comparison](https://www.buildmvpfast.com/api-costs/email) |
| | Postmark | From $15/mo for 10,000; best-in-class deliverability, separate transactional/marketing IP pools **[V]** | same |
| | Amazon SES | $0.10 per 1,000 emails, no base fee; you own suppression lists, bounce handling and reputation **[V]** | [SES analysis](https://www.saaspricepulse.com/blog/amazon-ses-pricing-per-1000-emails-2026) |
| **Transcription** | Deepgram Nova-3 | $0.0043/min batch (~$0.26/hour) **[V]** | [Deepgram](https://deepgram.com/learn/best-speech-to-text-apis-2026) |
| | AssemblyAI | From ~$0.15–0.37/hour depending on model **[V]** | [AssemblyAI](https://www.assemblyai.com/blog/speech-to-text-api-pricing) |
| | Bunny built-in | $0.10 per language-minute = $6/hour — **~23× Deepgram** **[V]** | [Bunny](https://bunny.net/docs/stream/pricing) |
| | Mux Robots premium captions | $0.0075/min (~$0.45/hour), experimental; caption translation $0.005/min **[V]** | [Mux](https://www.mux.com/docs/pricing.txt) |
| **Error tracking** | Sentry | Developer free (5K errors/mo, 1 user); Team $26/mo (50K errors); Business $80/mo **[V]** | [analysis](https://last9.io/blog/sentry-pricing/) |
| **CDN / DNS / WAF** | Cloudflare free tier | DNS, TLS, caching, basic DDoS protection at $0 **[V]** | — |
| **CI/CD** | GitHub Actions | Free tier ample for one repo at this size **[A]** | — |
| **Payments** | Paddle (MoR) / Stripe (if jurisdiction allows) | See §1.4 | — |

## 2.5 Explicitly not recommended at any stage below Scenario 3

Kubernetes. Microservices. Service mesh. Terraform-managed multi-account AWS. A dedicated search cluster. A data warehouse. Multi-region active-active. DRM. Each of these solves a problem this platform does not have, and each adds a permanent maintenance tax on what is realistically a one-to-three-person team. **[R]**

The brainstorm's own §6.11 guidance — start with basic search — is right: PostgreSQL full-text search with `pg_trgm` handles a curated catalogue of hundreds of courses with room to spare. Revisit only past roughly 2,000 catalogue items or when you need typo-tolerant multilingual relevance ranking. **[R]**

---

# 3. Candidate Deployment Architectures

## Architecture A — Ultra-Budget MVP

**Shape:** one VPS running everything except video and object storage.

```text
User
 │
 ▼
Cloudflare (free: DNS, TLS, CDN for static, basic DDoS)
 │
 ├──────────────► Cloudflare Stream ──► signed HLS playback
 │                (video storage, transcode, ABR, CDN)
 │
 └──► Hetzner VPS (Frankfurt), Docker Compose / Coolify
        ├── Reverse proxy (Caddy) — TLS, rate limiting
        ├── App container (web + API, server-rendered)
        ├── Worker container (transcription pipeline, cron, email)
        ├── PostgreSQL container  ──► nightly dump ──► Backblaze B2
        └── Redis container (queue + rate limits)

External: Cloudflare R2 (PDFs, images, VTT) · Deepgram (STT) ·
          Resend (email) · Paddle/Stripe (billing) · Sentry (errors)
```

**Designed for:** the first 100–500 users, one developer, minimum spend, maximum control.

**What you get:** total cost transparency, no per-service tax, no vendor metering surprises, trivially cheap staging (a second €5.49 box).

**What you own:** OS patching, Postgres upgrades, backup *and restore* verification, TLS renewal monitoring, disk-space alerts, and the fact that a single machine failure takes the whole product offline.

---

## Architecture B — Balanced Production *(recommended)*

**Shape:** managed platform for the app, managed Postgres, managed video, everything else pay-as-you-go.

```text
User
 │
 ▼
Cloudflare (DNS, TLS, WAF, caching)
 │
 ├──────────────► Video platform ──► signed HLS + VTT subtitles
 │                (Cloudflare Stream at MVP → Bunny Stream at scale)
 │
 └──► Render (Frankfurt)
        ├── Web service — Next.js/API, auto-deploy from main, health checks
        └── Worker service — queue consumer + cron
              │
              ├── Neon PostgreSQL (EU) — PITR, branching for staging
              ├── Upstash Redis — queue backend, rate limiting, cache
              ├── Cloudflare R2 — resources, images, subtitle files
              ├── Deepgram — batch transcription
              ├── Resend — transactional email
              └── Paddle (MoR) or Stripe — checkout, portal, webhooks

Observability: Sentry (errors) · Better Stack / UptimeRobot (uptime) ·
               platform logs · Cloudflare analytics
CI/CD: GitHub → Actions (test) → Render auto-deploy → manual rollback
```

**Designed for:** paying customers from day one, a solo developer or a team of two or three, predictable monthly cost, and the ability to stop thinking about servers.

**Why this shape:** the app and worker are separate processes so a slow transcription job cannot block a checkout webhook. The database is managed so PITR and backups are somebody else's job. Video never touches your infrastructure. Every component can be swapped independently because none of them are load-bearing on a proprietary API — except the payment provider, which is unavoidable.

---

## Architecture C — Scalable Production

**Shape:** redundant app tier, HA database, dedicated workers, bandwidth-priced video.

```text
User
 │
 ▼
Cloudflare (DNS, WAF, rate limiting, bot management)
 │
 ├──────────────► Bunny Stream (volume network) ──► signed HLS
 │                + Cloudflare R2 origin for source masters
 │
 └──► Load balancer
        ├── App node 1 ─┐
        ├── App node 2 ─┤ stateless, rolling deploys
        │               │
        ├── Worker node 1 ─┐ queue consumers, autoscaled by depth
        ├── Worker node 2 ─┘
        │
        ├── Managed PostgreSQL — primary + standby (HA) + read replica
        ├── Managed Redis — queue + cache, persistence enabled
        └── Staging environment (scaled-down mirror)

Observability: Sentry · Better Stack (uptime + logs) · APM ·
               queue-depth and video-spend dashboards
```

**Designed for:** 10,000+ users, real revenue, a team that can be paged, and a business where an hour of downtime costs more than the redundancy does.

---

## Architecture D — Cloudflare-native *(considered, not recommended yet)*

Workers/Pages for the app, D1 or Hyperdrive+Neon for data, R2 for files, Stream for video, Queues for jobs. Genuinely cheap and genuinely fast, with zero egress fees throughout.

**Why not now** **[R]**: the worker runtime constrains long-running transcription orchestration, Postgres access from Workers needs Hyperdrive or an HTTP driver, and the ecosystem maturity for a conventional server-rendered app with sessions, background jobs and heavy ORM use is still below that of a container platform. Revisit if your framework and ORM support it cleanly. The pieces you *should* adopt from it today — R2, Cloudflare DNS/WAF/CDN — are already in Architectures A, B and C.

---

# 4. Cost Analysis

All figures are monthly, in USD, excluding VAT, payment-processing fees and your own time. Hetzner and Bunny bill in EUR; ~$1.10/€1 assumed **[A]**.

## 4.1 Video cost by approach and scenario **[E]**

Built on the verified rates in §2.1 and the usage model in §1.3.

| Approach | S1 (10K min delivered) | S2 (100K min) | S3 (1M min) | Engineering burden |
|---|---:|---:|---:|---|
| **Cloudflare Stream** | **$28** | **$160** | **$1,180** | 🟢 none |
| **Mux (basic quality, 720p cap)** | **~$9** | **~$29** | **~$806** | 🟢 none |
| **Bunny Stream (volume network)** | **~$3** | **~$15** | **~$115** | 🟢 low |
| **Bunny Stream (standard, EU+NA only)** | ~$3 | ~$25 | ~$215 | 🟢 low |
| **Bunny Stream (standard, 40% MENA traffic)** | ~$8 | ~$73 | ~$615 | 🟢 low |
| **R2 + self-built transcode/HLS/signing** | ~$1 | ~$8 | ~$25 | 🔴 weeks of work, then permanent ownership |
| **Video on the app server** | "free" | fails | fails | 🔴 do not |

Workings: Stream = (catalogue min ÷ 1,000 × $5) + (delivered min ÷ 1,000 × $1). Mux = catalogue min × $0.0024 storage + (delivered − 100,000 free) × $0.0008, ignoring cold-storage discounts that would reduce it further. Bunny = ladder storage at ~40 MB/min × $0.01/GB + delivery at ~20 MB/min × regional rate.

**Reading of this table** **[R]**: Mux is *cheaper than Cloudflare Stream at MVP* because 100,000 delivered minutes per month are free and basic-quality encoding costs nothing — Scenario 1 and Scenario 2 delivery are entirely free. Bunny is 5–10× cheaper than either at scale but exposes you to bitrate and region risk. The Middle East & Africa standard-network rate is 6× the EU/NA rate, which matters directly if your learners are in the Maghreb — the volume network's flat $0.005/GB is the fix, at the cost of PoP selection.

## 4.2 Architecture A — Ultra-Budget MVP **[E]**

| Line item | S1 | S2 | S3 |
|---|---:|---:|---:|
| Hetzner VPS | $10 (CX33) | $18 (CX43) | $33 (CX53) |
| Hetzner automated backups (+20%) | $2 | $4 | $7 |
| Offsite DB backups (B2) | $1 | $1 | $3 |
| Video (Stream → Bunny at S3) | $28 | $160 | $115 |
| Object storage (R2) | $0 (free tier) | $0.40 | $2 |
| Email | $0 (Resend free) | $20 (Resend Pro) | $12 (SES) |
| Error tracking | $0 (Sentry free) | $26 (Team) | $40 |
| DNS/CDN/WAF | $0 (Cloudflare free) | $0 | $0 |
| **Total** | **~$41** | **~$229** | **~$212** |

The S3 column is *arithmetically* attractive and *operationally* indefensible: one machine, no failover, manual recovery, and 10,000 users' subscription state on a disk you own. Do not run Scenario 3 on Architecture A.

## 4.3 Architecture B — Balanced Production **[E]**

| Line item | S1 | S2 | S3 |
|---|---:|---:|---:|
| Workspace plan (Render) | $0 (Hobby) | $25 (Pro, flat) | $25 |
| Web service | $7 (Starter) | $25 (Standard) | $50 (2× Standard) |
| Worker service | $7 (Starter) | $7 | $50 (2× Standard) |
| PostgreSQL (Neon) | ~$15 | ~$35 | ~$130 (Scale) |
| Redis (Upstash) | $0 (free tier) | $3 | $25 |
| Object storage (R2) | $0 | $1 | $2 |
| Video | $28 (Stream) | $160 (Stream) | $115 (Bunny) |
| Transcription (amortised) | ~$5 | ~$10 | ~$20 |
| Email | $0 | $20 | $12 (SES) |
| Error tracking / uptime | $0 | $26 | $40 |
| **Total** | **~$62** | **~$312** | **~$469** |

If you stay on Cloudflare Stream through Scenario 3 instead of migrating to Bunny, S3 becomes **~$1,534**. That $1,065/month delta is the single largest cost decision in the entire architecture — and it only becomes relevant above roughly 300,000 delivered minutes/month.

## 4.4 Architecture C — Scalable Production **[E]**

| Line item | S2 | S3 |
|---|---:|---:|
| App nodes (2×, dedicated vCPU) | $100 | $200 |
| Worker nodes (2×) | $20 | $37 |
| Load balancer | $6 | $6 |
| Managed PostgreSQL, HA primary + standby | $61 | $122 |
| Read replica | — | $30 |
| Managed Redis | $15 | $15 |
| Staging environment | $25 | $40 |
| Video (Bunny volume + storage) | $25 | $130 |
| Object storage (R2) | $1 | $2 |
| Email (SES) | $2 | $12 |
| Monitoring (Sentry Team + Better Stack) | $26 | $56 |
| Backups + retention | $3 | $5 |
| **Total** | **~$284** | **~$655** |

Architecture C is not much more expensive than B at Scenario 3 — the difference is roughly $185/month for HA, a read replica and a staging mirror. What it actually costs is **operational attention**: you now own load-balancer config, rolling deploys, replica lag, failover testing and node patching.

## 4.5 Variables that dominate the bill, ranked

1. **Minutes of video delivered.** Everything else rounds to zero next to this. Doubling average watch time doubles the largest line item.
2. **Per-minute or per-GB video pricing model.** Same usage, 10× cost spread across providers.
3. **Blended delivery bitrate.** Under a GB-priced provider, capping at 720p instead of 1080p cuts delivery bandwidth by roughly half. Under a minute-priced provider it changes nothing — which is exactly why the two models suit different platforms.
4. **Catalogue hours stored.** A curated platform controls this directly; an open marketplace does not. This is a genuine structural advantage of your product decision.
5. **Whether the database is always-on or metered.** A metered database at 1 CU costs ~$76/month; the same workload at 0.25 CU costs ~$19 **[E]**.
6. **Number of separately-billed services.** Five services at $7 is $35 for compute you could get on one $10 VPS. Managed platforms charge per box, not per CPU.

## 4.6 Hidden costs

| Hidden cost | Why it bites | Mitigation |
|---|---|---|
| **Egress from your app platform** | Railway $0.05/GB, Render/Vercel ~$0.15/GB. Streaming even one video through your API turns a $7 service into a $200 bill | Never proxy media through the app. Always redirect to a signed CDN URL |
| **Buffered-but-unwatched video** | Mux bills minutes *delivered*, including player pre-buffer. Autoplay previews and multiple players per page multiply this **[V]** | `preload="none"`, lazy-load players, one player per page, pause on tab-hidden |
| **Prepaid video storage granularity** | Cloudflare Stream storage is bought in $5 / 1,000-minute increments **[V]** | Budget in blocks, monitor headroom |
| **Regional bandwidth multipliers** | Bunny standard network: $0.060/GB Middle East & Africa vs $0.010 EU/NA — 6× **[V]** | Volume network flat $0.005/GB, or accept the premium knowingly |
| **Always-on metered database** | Serverless Postgres only saves money when it sleeps; production traffic keeps it awake around the clock | Cap autoscaling; compare against a flat-rate instance monthly |
| **Storage that only grows** | Render Postgres storage can be increased but never decreased **[V]** | Size deliberately; prune event/log tables on a schedule |
| **Object storage minimums** | R2 Infrequent Access has a 30-day minimum duration plus a $0.01/GB retrieval fee **[V]** | Keep active lesson resources in Standard |
| **Error-tracking spikes** | One bad deploy can generate hundreds of thousands of events and a surprise invoice **[V]** | Set a Sentry spend cap and inbound filters on day one |
| **Orphaned media** | The brainstorm flags this (§6.15): deleted courses leave files and video assets billing forever | Lifecycle policy + a scheduled reconciliation job comparing DB rows to storage objects |
| **Re-transcription** | Every instructor re-upload re-runs STT and re-encodes | Content-hash uploads; only reprocess on actual change |
| **Staging** | A full mirror can double compute, database and monitoring lines | Use database branching; scale staging to the smallest tier; sleep it out of hours |
| **Payment fees** | ~5% + fixed fee under an MoR — at MVP this exceeds your entire infrastructure spend | Price the subscription with this margin built in from the start |
| **Provider price changes** | Hetzner raised some cloud instance prices by up to ~3.1× in June 2026 **[V]** | Keep everything portable; avoid annual prepayment on volatile lines |
| **Your own time** | Twelve hours a month of ops on Architecture A is not free | Value it honestly against the ~$20/month that Architecture B costs extra |

---

# 5. Provider Comparison

## 5.1 Application hosting

| Criterion | Hetzner + Coolify | Render | Railway | Vercel | Fly.io |
|---|---|---|---|---|---|
| **Entry price** | €5.49–15.99/mo flat **[V]** | $7/service **[V]** | $5/mo + metered **[V]** | $20/seat + metered **[V]** | metered |
| **Free tier** | none | yes, sleeps after 15 min **[V]** | trial credit only **[V]** | Hobby, non-commercial **[V]** | limited |
| **Compute model** | fixed VPS | fixed per-service tiers | per-second vCPU/RAM | per-CPU-ms, Fluid Compute | per-machine |
| **Database** | self-hosted | managed, same platform | managed, same platform | external only | managed PG |
| **Included bandwidth** | 20 TB (EU) | 100 GB/workspace, then ~$0.15/GB **[V]** | metered $0.05/GB **[V]** | 1 TB Pro, then $0.15/GB **[V]** | metered |
| **Scalability** | vertical; manual horizontal | manual or CPU-based autoscaling | vertical-first | automatic, serverless | multi-region |
| **Reliability** | you own it | platform SLA | platform SLA | platform SLA | platform SLA |
| **Regions near Morocco** | Falkenstein, Nuremberg, Helsinki | Frankfurt | EU | global edge | CDG, AMS |
| **Deployment simplicity** | 🟡 Coolify/Compose setup | 🟢 git push | 🟢 git push | 🟢 git push | 🟡 flyctl + config |
| **CI/CD** | you wire it | built in | built in | built in | built in |
| **Monitoring** | you install it | basic built in | basic built in | good built in | basic |
| **Backups** | you script them | managed for DB | managed for DB | n/a | managed for DB |
| **Vendor lock-in** | none | low (Docker) | low (Docker) | **high** (framework + runtime coupling) | low |
| **Documentation** | good | very good | good | excellent | good |
| **Developer experience** | 🟡 | 🟢 | 🟢 | 🟢🟢 | 🟡 |
| **Suitability here** | best for cost, worst for sleep | **best fit** | good; bill less predictable | over-priced for a stateful monolith with workers | more capability than needed |

## 5.2 Database

| Criterion | Neon | Supabase | DigitalOcean | Render PG | Self-hosted |
|---|---|---|---|---|---|
| **Entry price** | $0 free tier; usage-based, no minimum **[V]** | $0 free; Pro $25/mo **[V]** | $15/mo **[V]** | $6/mo **[V]** | $0 marginal |
| **Realistic prod cost (S2)** | ~$35 **[E]** | $25 + compute **[V]** | $60.90 **[V]** | ~$25 **[E]** | $0 |
| **HA** | no user-selectable standby on Launch | on higher tiers | +$30/mo standby **[V]** | higher tiers | you build it |
| **PITR** | yes | yes on Pro | yes **[V]** | higher tiers only **[V]** | you build it |
| **Read replicas** | on Scale | yes | $15/mo each **[V]** | higher tiers | you build it |
| **Branching for staging** | **yes, copy-on-write** | no | no | no | no |
| **Storage pricing** | $0.35/GB-mo **[V]** | included then metered | bundled with tier | $0.30/GB-mo, increase-only **[V]** | disk price |
| **Lock-in** | none (plain Postgres) | medium if you use Auth/Storage/Realtime | none | none | none |
| **Suitability here** | **best fit** — branching gives free staging, PITR included, cost tracks usage | strong if you adopt the whole bundle; you have already specified your own auth and entitlement logic | best if you want a flat, boring, predictable bill | fine if the app is on Render and you accept the tier gates | only with Architecture A |

## 5.3 Video

| Criterion | Cloudflare Stream | Mux | Bunny Stream | R2 + own pipeline |
|---|---|---|---|---|
| **Pricing model** | per minute stored + delivered | per minute encoded/stored/delivered, resolution-tiered | per GB stored + delivered | per GB stored, free egress |
| **Encoding cost** | free **[V]** | free at basic quality **[V]** | free for standard H.264 **[V]** | your compute |
| **Free allowance** | none | **100,000 delivered min/month** **[V]** | none ($1/mo minimum) **[V]** | 10 GB storage **[V]** |
| **Adaptive bitrate** | automatic | automatic, just-in-time | automatic | you build it |
| **Signed URLs** | yes, with geo/IP rules **[V]** | yes | yes (token auth) | you build it |
| **DRM** | no **[V]** | add-on: $100/mo + $0.003/license **[V]** | $99/mo + per-license **[V]** | no |
| **Captions/subtitles** | supported | auto captions available; Robots premium captions ~$0.0075/min **[V]** | AI transcription $0.10/language-min — expensive **[V]** | your own VTT |
| **Analytics** | basic | **best in class**, included **[V]** | good, includes engagement heatmaps | none |
| **Cost at S3** | $1,180 **[E]** | $806 **[E]** | $115–615 depending on network/region **[E]** | ~$25 + your labour **[E]** |
| **Predictability** | 🟢 highest — bitrate-independent | 🟢 high | 🟡 varies with bitrate and geography | 🟡 |
| **Suitability here** | best MVP simplicity | **best MVP economics + analytics**, and audio-only lessons bill at 1/10 rate | best at scale | only if video becomes your core competency |

---

# 6. Reliability & Production Readiness

> A provider's SLA covers the provider. It says nothing about whether *your* application is reliable. Every architecture below needs work that no vendor will do for you.

## 6.1 Architecture A

| Dimension | Reality |
|---|---|
| **Single points of failure** | Everything. One host, one disk, one Postgres, one Redis, one network path |
| **Backups** | You script `pg_dump`, encrypt it, ship it offsite, rotate it, and **verify restores** |
| **Disaster recovery** | Manual. Realistic RTO measured in hours; RPO equals your backup interval |
| **Database reliability** | No automatic failover. A bad `apt upgrade` can take Postgres down |
| **Monitoring** | Nothing until you install it |
| **Health checks / rollback** | Whatever Coolify or your Compose setup provides; rollback is redeploying the previous image tag |
| **SSL/TLS** | Automatic via Caddy/Traefik; you must monitor renewal |
| **Secrets** | `.env` on the host. Anyone with SSH has everything |
| **DDoS** | Cloudflare free tier absorbs the common cases, provided the origin IP never leaks |

**Required to make it genuinely production-ready:** automated encrypted offsite backups **with a monthly restore drill**, uptime monitoring with alerting to a phone, Postgres connection and disk alerts, `ufw` closing everything but 80/443, SSH keys only, unattended security upgrades, a documented rebuild runbook, and origin IP hidden behind Cloudflare.

## 6.2 Architecture B

| Dimension | Reality |
|---|---|
| **Single points of failure** | One app instance (restartable), one DB primary. Video and storage are independently redundant |
| **Backups** | Managed, with PITR. **You still must test a restore** |
| **Disaster recovery** | Restore to a branch, repoint `DATABASE_URL`. RTO in minutes if rehearsed |
| **Database reliability** | Managed failover; no user-selectable standby on entry tiers |
| **Monitoring** | Sentry + uptime checks + platform metrics. Add queue-depth alerts yourself |
| **Deploys / rollback** | Automatic on merge; one-click rollback to previous deploy |
| **SSL/TLS** | Fully managed |
| **Secrets** | Platform environment variables, encrypted at rest, not in git |
| **Rate limiting** | **Yours to build** — at Cloudflare and again in-app on auth, signup and password reset |

**Required additions:** webhook idempotency (a duplicate `subscription.updated` must not double-extend access), a dead-letter queue for failed transcription jobs, a reconciliation cron that compares your entitlement table against the payment provider's source of truth, structured logging with request IDs, and a documented on-call path even if the rota is one person.

## 6.3 Architecture C

Adds redundant app nodes, a hot standby database, a read replica and a staging mirror. Removes the app tier and database as single points of failure. **Introduces** new failure modes: replica lag producing stale reads, split-brain during failover, load-balancer misconfiguration, and deploy skew between nodes. Requires failover drills — an untested standby is a liability, not a safety net.

## 6.4 Reliability truths specific to this platform

1. **The webhook boundary is your highest-risk surface.** A dropped or duplicated billing webhook silently corrupts entitlement. Verify signatures, store the raw event, process idempotently by event ID, retry with backoff, and reconcile nightly. The brainstorm's §11 "Entitlement Consistency" and §6.10 "Subscription diagnostics" are reliability requirements, not features.
2. **Backups are worthless until restored.** Schedule a quarterly restore drill into a scratch environment and time it.
3. **The transcription pipeline will fail often** — bad audio, unsupported codecs, provider timeouts. It needs explicit states, retry limits, a dead-letter queue and an admin view. The brainstorm already calls for processing status and failure handling; treat that as infrastructure.
4. **Video outages are visible outages.** Your player must degrade gracefully when signed URL minting fails, and you should monitor playback error rates, not just HTTP 200s.
5. **Trials and renewals are time-based.** Cron reliability is user-visible: a missed sweep means people keep access they have not paid for, or lose access they have.

---

# 7. Scalability Analysis

## 7.1 How each architecture grows

| Lever | A (single VPS) | B (managed PaaS) | C (redundant) |
|---|---|---|---|
| **Vertical scaling** | Resize the VPS, brief reboot. €5.49 → €29.49 covers a long way | Change instance tier, rolling restart | Same, per node |
| **Horizontal scaling** | Not practical without re-architecting | Add replicas — requires a stateless app | Native, behind the LB |
| **Database scaling** | Vertical only; then you must migrate | Increase compute; add replica on higher tier | Standby + read replica; then partitioning |
| **Caching** | Local Redis | Managed Redis + Cloudflare edge cache | Same + application-level caching |
| **Background workers** | Same box — competes with web traffic | Separate service, scale independently | Autoscaled worker pool |
| **Queues** | Redis-backed (BullMQ or equivalent) | Same | Same, with depth-based autoscaling |
| **Object storage** | Effectively unlimited | Unlimited | Unlimited |
| **Video delivery** | Provider's problem at every tier | Provider's problem | Provider's problem |
| **Load balancing** | none | platform-provided | explicit LB with health checks |

## 7.2 Statelessness is the thing that decides your ceiling

Nothing about scaling works if the app keeps state locally. Three rules from day one, at zero cost **[R]**:

- Sessions in Postgres or Redis, never in process memory.
- Uploads go to object storage via presigned URLs, never to local disk.
- Scheduled work runs in the worker process with a distributed lock, never as a timer inside a web process that may one day have two replicas.

Follow these and moving from A to B to C is a configuration change. Break them and it is a rewrite.

## 7.3 Where the MVP architecture runs out

| Signal | What it means | Move to |
|---|---|---|
| Sustained CPU >70% or p95 latency >800 ms | Web tier saturated | Bigger instance, then a second replica |
| Transcription backlog growing across a day | Worker starved | Separate worker service, then more workers |
| DB connections exhausted | Missing pooling | PgBouncer / platform pooler |
| Reporting queries slowing the app | Read contention | Read replica |
| Video delivery >300,000 min/month | Per-minute pricing now costs more than per-GB | Migrate video provider (§10, Stage 3) |
| Any downtime that costs a paying customer | Single-instance risk is now expensive | Architecture C |
| Catalogue >~2,000 items or multilingual relevance complaints | Postgres FTS at its limit | Dedicated search engine |

Concretely: **Architecture A comfortably holds Scenario 1 and most of Scenario 2** (a €15.99 CX43 with 4 vCPU and 8 GB is a lot of machine for 200 DAU). It becomes untenable not because of load but because of **risk** — the moment recurring revenue makes hours of downtime unacceptable.

---

# 8. Video-Specific Analysis

Video deserves its own section because it is 60–85% of the bill, the hardest thing to migrate later, and the feature most likely to sink an MVP timeline.

## 8.1 Approach 1 — Video files on the application server

**Cost:** appears free. **Reality:** you get no transcoding, so a 2 GB instructor upload is served as-is to a phone on 4G; no adaptive bitrate, so playback stalls; disk fills; egress is billed at platform rates ($0.05–0.15/GB), meaning **one 20 GB month costs more than the server**; and every concurrent viewer consumes app-server bandwidth and connections that should be serving API requests.

**Verdict:** not viable. The brainstorm reached the same conclusion (Trap 1) and it is correct. **[R]**

## 8.2 Approach 2 — Object storage + CDN (R2 or B2 + Cloudflare/Bunny)

**Cost:** the cheapest possible — roughly $25/month at Scenario 3 **[E]**, with R2 egress at zero **[V]** or B2 egress free through CDN partners **[V]**.

**What you must build:** an ffmpeg transcoding pipeline (multiple renditions, correct keyframe alignment), HLS packaging and manifest generation, a job queue with retries for encoding, signed-URL minting at the edge for both manifests and segments, hotlink protection, a player integrated with your token scheme, thumbnail generation, and monitoring for all of it. Plus ongoing maintenance as codecs and browsers change.

**Verdict:** correct at large scale or if video delivery becomes a core competency. Wrong for an MVP that has not yet proved anyone will subscribe. **[R]**

## 8.3 Approach 3 — Managed video platform (recommended)

Cloudflare Stream, Mux and Bunny Stream all give you upload → transcode → ABR HLS → global CDN → signed playback with no pipeline to maintain.

| | Cloudflare Stream | Mux | Bunny Stream |
|---|---|---|---|
| Time to first working player | hours | hours | hours |
| Cost at MVP (S1) **[E]** | $28 | **~$9** | ~$3 |
| Cost at scale (S3) **[E]** | $1,180 | $806 | $115–615 |
| Bitrate risk | none (per-minute) | none (per-minute) | yes (per-GB) |
| Region risk | none | none | MEA is 6× EU on standard network **[V]** |
| Engagement analytics | basic | **best** | good |
| Audio-only lessons | billed as video | **1/10 rate** **[V]** | billed by size (naturally cheap) |

**Recommendation for MVP: Mux, basic video quality, capped at 720p delivery.** **[R]**

Reasoning:
- **Encoding is free** at basic quality, and the first **100,000 delivered minutes each month are free** **[V]** — which covers Scenario 1 *and* Scenario 2 delivery entirely.
- Language content is talking-head, low-motion footage. The reduced basic ladder is visually adequate for it; you can selectively use `plus` quality for flagship courses.
- **Audio-only lessons cost one tenth of 720p video** across encoding, storage and delivery **[V]**. The brainstorm explicitly plans audio-only lessons, so this is a direct, structural saving.
- **Automatic cold storage** discounts unwatched assets by 40% after 30 days and 60% after 90 **[V]** — exactly the profile of a growing course back-catalogue.
- Mux Data engagement analytics are included with delivery **[V]**, and they answer the brainstorm's own Phase 1 success metrics (lesson completion rate, drop-off points) without a separate analytics build.
- `max_resolution=720p` on the playback URL caps delivery cost, and `preload="none"` plus lazy-loaded players prevents paying for video nobody watched **[V]**.

**Acceptable alternative:** Cloudflare Stream, if you would rather have DNS, WAF, object storage and video on one vendor and one invoice. It costs about $19/month more at MVP **[E]** and buys real simplicity.

## 8.4 Transcription within the video pipeline

| Provider | Rate | 60 h catalogue | 600 h catalogue |
|---|---|---:|---:|
| Deepgram Nova-3 batch | $0.0043/min **[V]** | $15 | $155 |
| AssemblyAI | ~$0.15–0.37/hour **[V]** | $9–22 | $90–222 |
| Mux Robots premium captions | $0.0075/min **[V]** | $27 | $270 |
| Bunny built-in AI transcription | $0.10/language-min **[V]** | $360 | $3,600 |

**Recommendation: a dedicated STT API (Deepgram Nova-3 or AssemblyAI), not the video platform's bundled transcription.** **[R]** Three reasons: it is 10–25× cheaper than Bunny's bundled option; you get word-level timings you own and can store, edit and re-publish independently; and it decouples subtitles from the video vendor, so migrating video later does not mean re-transcribing the catalogue.

Store transcripts as **structured rows in Postgres** (segment, start, end, text, reviewed flag) and render VTT on demand or on publish. This makes the review/edit workflow, interactive transcripts and future translated subtitles all straightforward, and it makes the subtitle data portable. **[R]**

**The real transcription cost is human review, not API spend.** At $155 for 600 hours of machine transcription, budget is irrelevant; reviewer hours are the constraint. Design the admin review UI accordingly.

## 8.5 Access control

At MVP **[R]**:
- Short-lived signed playback tokens (minutes, not hours), minted server-side **only after an entitlement check**.
- Never embed a permanent playback ID in HTML for gated content.
- Restrict allowed origins/referrers at the video provider.
- Log playback token issuance per user for abuse detection.

**Skip DRM at MVP.** It costs $99–100/month plus per-license fees **[V]**, complicates the player, and does not stop screen recording. Signed URLs plus abnormal-usage detection is the right level of protection for a subscription language course. Revisit only if you find organised redistribution. This matches the brainstorm's own decision to exclude DRM from MVP.

---

# 9. Recommended Architecture

## 9.1 The stack

```text
                          Learner / Instructor / Admin
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  Cloudflare — DNS, TLS, WAF,   │
                    │  caching, rate limiting        │
                    └────────────────────────────────┘
                          │                    │
      signed playback     │                    │  app traffic
              ┌───────────┘                    ▼
              ▼                   ┌──────────────────────────┐
   ┌────────────────────┐         │  Render (Frankfurt)      │
   │  Mux Video         │         │                          │
   │  transcode, ABR,   │◄────────┤  Web service             │
   │  HLS, CDN,         │  signed │  (SSR app + API)         │
   │  playback tokens,  │  tokens │                          │
   │  engagement data   │         │  Worker service          │
   └────────────────────┘         │  (queue + cron)          │
                                  └───────────┬──────────────┘
                                              │
        ┌───────────────┬──────────────┬──────┴───────┬──────────────┐
        ▼               ▼              ▼              ▼              ▼
  ┌───────────┐  ┌────────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐
  │  Neon     │  │  Upstash   │  │Cloudflare │  │ Deepgram │  │  Resend  │
  │ Postgres  │  │   Redis    │  │    R2     │  │   STT    │  │  email   │
  │ PITR +    │  │ queue,     │  │ PDFs,     │  │ batch    │  │          │
  │ branching │  │ rate limit │  │ images,   │  │ timings  │  │          │
  └───────────┘  └────────────┘  │ VTT       │  └──────────┘  └──────────┘
                                 └───────────┘
                                              │
                                              ▼
                                  ┌──────────────────────────┐
                                  │  Paddle (merchant of     │
                                  │  record) — checkout,     │
                                  │  portal, webhooks, tax   │
                                  │  [or Stripe Billing if   │
                                  │   jurisdiction allows]   │
                                  └──────────────────────────┘

Observability: Sentry (errors) · Better Stack or UptimeRobot (uptime)
CI/CD: GitHub → Actions (lint, test, migrate check) → Render auto-deploy
```

## 9.2 Component justification

### Render — application and worker hosting
- **Why needed:** something has to run the server-rendered app, the API and the background jobs.
- **Why chosen:** flat per-service pricing you can predict a year out; a Frankfurt region ~40 ms from Morocco and close to European learners; separate web and worker services on the same platform; git-push deploys with one-click rollback; managed TLS; per-seat fees removed from paid workspace plans in April 2026 **[V]**.
- **Alternatives considered:** Railway (excellent DX, but per-second metering makes the bill harder to forecast — a real drawback when video already introduces variance); Fly.io (multi-region capability you do not need); Vercel (expensive for a stateful monolith with long-running workers, and the highest lock-in); Hetzner + Coolify (cheaper, but you become the ops team).
- **Cost:** $14/mo at MVP → ~$100/mo at Scenario 3 **[E]**.
- **Migration path:** the app is a container. Moving to Railway, Fly or a Hetzner box is a rebuild-and-redeploy, not a rewrite — provided §7.2 statelessness is respected.

### Neon — PostgreSQL
- **Why needed:** subscriptions, entitlements, progress and transcripts are relational, transactional data with audit requirements.
- **Why chosen:** plain Postgres with no proprietary layer; PITR included; **copy-on-write branching gives you a production-shaped staging database for near-nothing**, which directly serves the brainstorm's demand for subscription and trial diagnostics; usage-based with no monthly minimum since December 2025 **[V]**.
- **Alternatives considered:** Supabase (great value if you adopt Auth/Storage/Realtime — but you have specified your own role, entitlement and approval logic, so the bundle is mostly unused and adds lock-in); DigitalOcean (more predictable flat bill, no branching — a fine swap if you prefer boring); self-hosted (Architecture A only).
- **Cost:** ~$15/mo at MVP → ~$130/mo at Scenario 3 **[E]**.
- **Migration path:** `pg_dump`/`pg_restore` to any Postgres anywhere. Lowest lock-in of any component here. Keep migrations in the repo and avoid provider-specific extensions.

### Mux — video
- **Why needed:** transcoding, ABR, global delivery, signed playback and player compatibility are a multi-month build you should not attempt pre-PMF. This is the brainstorm's own guidance.
- **Why chosen:** free encoding at basic quality, 100,000 free delivered minutes/month, audio-only at one tenth the video rate, automatic cold-storage discounts, and included engagement analytics **[V]** — see §8.3.
- **Alternatives considered:** Cloudflare Stream (simpler single-vendor story, ~$19/mo more at MVP); Bunny Stream (5–10× cheaper at scale, but per-GB pricing exposes you to bitrate and MENA-region multipliers); R2 + own pipeline (cheapest and by far the most work).
- **Cost:** ~$9/mo at MVP → ~$806/mo at Scenario 3 **[E]**.
- **Migration path:** the real one. Store the source master of every lesson in **R2, yourself** — never rely on the video provider as your only copy. Keep a `video_provider` + `video_asset_id` pair on the lesson record rather than a hard-coded URL. Then switching to Bunny is a re-upload script and a config change, not a data-recovery exercise. **This single decision preserves your ability to cut the largest line item on the bill.**

### Cloudflare R2 — object storage
- **Why needed:** PDFs, worksheets, vocabulary lists, images, subtitle files, and the video source masters above.
- **Why chosen:** zero egress at any volume **[V]**, S3-compatible so any SDK works, 10 GB free tier covers MVP entirely **[V]**.
- **Alternatives considered:** Backblaze B2 (cheaper per TB at $6/TB **[V]**, free egress through CDN partners — better once masters exceed a few TB); S3 (egress fees make it the most expensive for serving).
- **Cost:** $0 at MVP → ~$2/mo at Scenario 3 **[E]**.
- **Migration path:** S3-compatible API means `rclone` to anywhere.

### Upstash Redis — queue, cache, rate limiting
- **Why needed:** the transcription pipeline needs a durable job queue; auth endpoints need rate limiting; entitlement lookups benefit from caching.
- **Why chosen:** free tier of 256 MB / 500K commands per month covers MVP **[V]**; scales to zero cost when idle; speaks both the Redis protocol and HTTP.
- **Alternatives considered:** Redis on the app platform (fine, but a fixed $10+/mo for an idle queue); self-hosted (Architecture A only).
- **Cost:** $0 at MVP → ~$25/mo at Scenario 3 **[E]**.
- **Migration path:** standard Redis protocol; swap the connection string.
- **Caveat:** per-command billing punishes chatty polling loops. Use blocking pops and sane poll intervals.

### Deepgram — transcription
- **Why needed:** transcripts and subtitles are a core learning feature, not an accessibility afterthought.
- **Why chosen:** ~$0.26/hour batch **[V]** with word-level timings; the entire Scenario 3 catalogue costs ~$155 **[E]**.
- **Alternatives considered:** AssemblyAI (comparable price, strong accuracy, richer transcript intelligence — a straight swap); Mux Robots captions (convenient but couples subtitles to the video vendor); Bunny built-in ($6/hour **[V]** — rejected on cost); self-hosted Whisper (free API cost, but you now run GPU infrastructure).
- **Cost:** ~$5/mo amortised at MVP **[E]**.
- **Migration path:** abstract behind a single `TranscriptionProvider` interface. Store the normalised segments, not the vendor response.

### Resend → Amazon SES — email
- **Why needed:** the brainstorm's critical email list (verification, reset, trial started/ending, payment succeeded/failed, cancelled, expired) is subscription-critical, not optional.
- **Why chosen:** 3,000 emails/month free **[V]** covers MVP; excellent DX; move to SES at $0.10 per 1,000 **[V]** when volume makes the difference material (~$12/mo vs ~$40+/mo at 120,000 emails **[E]**).
- **Alternatives considered:** Postmark (best deliverability, separate transactional/marketing IP pools **[V]** — worth the premium if trial-conversion emails start landing in spam).
- **Cost:** $0 → ~$12/mo **[E]**.
- **Migration path:** send through one internal `EmailService`. Never call a vendor SDK from a route handler.

### Paddle (or Stripe) — payments
- **Why needed:** subscriptions with hosted checkout, a customer portal, invoices, dunning and webhook-driven state — all MVP must-haves in the brainstorm.
- **Why chosen:** if the entity is Moroccan, Stripe is unavailable **[V]** and an MoR that supports global sellers is the only clean path; Paddle states worldwide seller support excluding sanctioned countries **[V]**, and also removes VAT/sales-tax handling from your roadmap.
- **Alternatives considered:** Stripe Billing (best API and docs — use it if you incorporate in a supported jurisdiction); Polar (developer-friendly MoR, narrower payout country list **[V]**); Lemon Squeezy (in transition into Stripe Managed Payments **[V]**); a licensed local Moroccan PSP (best for local card acceptance and MAD settlement, weaker for global subscriptions).
- **Cost:** ~5% + fixed fee per transaction **[A]** — verify current rates directly.
- **Migration path:** **the hardest migration in the stack.** Card credentials do not transfer between merchants of record; switching means re-authorising every subscriber. Mitigate by keeping your own `subscriptions` and `entitlements` tables as the application's source of truth, with the provider as an upstream event feed. Never scatter provider-specific IDs through business logic.

### Cloudflare — DNS, TLS, WAF, CDN
- **Why needed:** origin protection, edge caching for the public catalogue, rate limiting before traffic reaches your app, and bot mitigation on signup (the brainstorm flags trial abuse as Trap 6).
- **Why chosen:** the free tier does all of this competently. **[V]**
- **Cost:** $0.
- **Migration path:** DNS is portable; edge rules are not, but they are small.

## 9.3 Estimated total

| Scenario | Infrastructure | Payment fees (excluded above) |
|---|---:|---|
| S1 — 100 users, 20 DAU | **~$62/mo** **[E]** | ~5% of revenue |
| S2 — 1,000 users, 200 DAU | **~$312/mo** **[E]** | ~5% of revenue |
| S3 — 10,000 users, 2,000 DAU | **~$469/mo** with video migrated to Bunny; **~$1,534/mo** if you stay on per-minute video **[E]** | ~5% of revenue |

At Scenario 2, with 1,000 users of whom (say) 300 are paying $10/month, infrastructure is roughly 10% of revenue. That is a healthy ratio for a video-heavy education product.

---

# 10. Deployment Evolution Strategy

```text
Stage 1 — Cheap MVP                    ~$62/mo
Single web + worker on Render · Neon · Mux · R2 · Upstash free tier
Goal: prove people subscribe. Optimise for shipping speed, not uptime.
        │
        │  TRIGGER: first paying customers, or any real revenue at risk
        ▼
Stage 2 — Production Hardening         ~$120–180/mo
Uptime monitoring + alerts · restore drill · Sentry with spend cap ·
webhook idempotency + nightly entitlement reconciliation ·
staging via Neon branch · Cloudflare WAF + auth rate limits ·
DLQ for transcription jobs
Goal: stop losing money to silent failures. Little new spend; mostly work.
        │
        │  TRIGGER: p95 latency degrading, worker backlog, >500 DAU
        ▼
Stage 3 — Growing Traffic              ~$300–500/mo
Larger web instance, then a second replica · dedicated worker service ·
DB compute increase + connection pooling · read replica for reporting ·
MIGRATE VIDEO to per-GB pricing when delivery >300,000 min/month
Goal: keep the experience fast while the bill stays sub-linear.
        │
        │  TRIGGER: downtime now costs more than redundancy
        ▼
Stage 4 — Large-Scale Infrastructure   ~$650–1,200/mo
HA database with standby · 2+ app nodes behind an LB · autoscaled workers ·
full staging mirror · APM + tracing · regional delivery tuning ·
DRM only if piracy is measured, not feared
Goal: survive node failure without a human. Still no Kubernetes.
```

## 10.1 Migration triggers, stated precisely

| Trigger | Action | Why wait for it |
|---|---|---|
| First paid subscription | Begin Stage 2 immediately | Before revenue, downtime costs nothing but pride |
| Sustained CPU >70% or p95 >800 ms | Scale the web instance vertically | Vertical is one click; horizontal needs statelessness proven |
| Transcription backlog persists >4 h | Split the worker onto its own service | Keeps checkout webhooks off the same CPU as ffmpeg-adjacent work |
| Reporting queries slow the app | Add a read replica | Cheaper and simpler than a warehouse |
| **Video delivery >300,000 min/month** | Migrate video provider to per-GB pricing | Below this, per-minute simplicity is worth more than the saving; above it, the gap becomes hundreds of dollars a month **[E]** |
| An outage costs a customer | Architecture C: HA database, second app node | Redundancy before this point is paying for insurance against a loss you cannot yet suffer |
| Catalogue >~2,000 items or relevance complaints | Dedicated search engine | Postgres FTS handles a curated catalogue easily |
| Multiple engineers deploying daily | Full staging mirror, preview environments | Branch-based staging is enough for one or two people |

## 10.2 What "not painting yourself into a corner" concretely means

Six decisions, all free to make now, all expensive to retrofit **[R]**:

1. **Own the video source masters in your own object storage.** This is what makes the largest cost line migratable.
2. **Keep the app stateless** (§7.2).
3. **Treat your database as the source of truth for entitlement**, with the payment provider as an event feed — not the reverse.
4. **Put every third-party integration behind a thin interface** — video, STT, email, payments. Four small files that will save you weeks.
5. **Store transcripts as structured data**, not as vendor-formatted caption files.
6. **Keep schema migrations in the repository** and never apply changes by hand in a console.

---

# 11. Security Considerations

## 11.1 Deployment-level

| Area | Requirement | Notes |
|---|---|---|
| **Environment variables** | Never in git. Platform-managed, encrypted at rest. Separate values per environment | On a VPS, a `.env` readable by anyone with SSH is your weakest link |
| **Secrets management** | Rotate on staff change; use a password manager or vault for the humans; scope API keys narrowly | Separate write vs read-only keys for object storage |
| **Database access** | Never publicly reachable. TLS enforced. Least-privilege application role, separate migration role | Managed providers give you a private connection string — use it |
| **Network isolation** | Web and worker talk to the DB over the platform's private network where available; firewall closes everything except 80/443 | Hide the origin behind Cloudflare so the IP cannot be attacked directly |
| **HTTPS/TLS** | Enforced everywhere, HSTS, redirect HTTP, secure + `SameSite` cookies | Free and automatic on all recommended platforms |
| **CORS** | Explicit allow-list. No wildcard on credentialed endpoints | |
| **CSRF** | Tokens on all state-changing form posts; `SameSite=Lax` minimum | |
| **Rate limiting** | At Cloudflare *and* in-app on login, signup, password reset, trial start, checkout initiation | Trap 6 in the brainstorm is trial abuse — this is where you stop it |
| **API protection** | Every route re-checks role and entitlement server-side. Never trust a client-supplied `courseId` without an ownership check | |
| **Dependency security** | Dependabot/Renovate, `npm audit` in CI, pinned lockfiles | |
| **CI/CD security** | Least-privilege deploy tokens, no secrets in build logs, required review on the default branch, protected production branch | |
| **Backups** | Encrypted at rest, stored with a *different* provider than the primary database, restore tested quarterly | A backup in the same account as the database is not a backup |

## 11.2 Specific to an education platform with accounts and payments

1. **Entitlement is enforced server-side, on every request, at the data layer.** Hiding a "locked" badge in the UI is not access control. Every lesson fetch, every playback-token mint, every resource download re-derives entitlement from subscription state.
2. **Never handle card data.** Hosted checkout and a hosted customer portal only — the brainstorm's own principle. This keeps you out of PCI scope almost entirely.
3. **Verify every webhook signature** and process idempotently by event ID. An unverified billing webhook endpoint is a free-subscription API for anyone who finds it.
4. **Signed, short-lived playback tokens minted only after an entitlement check**, with origin restrictions at the video provider. Log issuance per user; alert on abnormal volume (many tokens, many IPs, one account — an account-sharing signal, which is the realistic piracy vector for subscription courses).
5. **Uploads are the instructor-side attack surface.** Presigned direct-to-storage uploads with enforced content type and size limits; validate server-side after upload; store in a bucket that is **not** served from your application domain; never trust the client-supplied filename or MIME type.
6. **Personal data.** The brainstorm's GDPR baseline (privacy policy, terms, export process, deletion process, consent) needs a deployment counterpart: EU-region hosting, a documented data map, and a deletion routine that also purges object storage and video assets — not just database rows.
7. **Jurisdictional data protection.** If the operating entity is Moroccan, personal-data processing falls under Moroccan data-protection law with its own regulator and registration/declaration expectations, in addition to GDPR where EU learners are involved. **[A] — verify with local counsel; I have not confirmed the current filing requirements from a primary source.**
8. **Admin actions must be audit-logged.** Manual access overrides, refunds and role changes are all MVP admin features in the brainstorm and all are abuse vectors. Log actor, target, action, timestamp, reason — immutably.
9. **Minors.** If under-18 learners are plausible, age-gating, guardian consent and data-minimisation obligations change materially. Decide this deliberately rather than by default. **[R]**

---

# 12. Operational Complexity

| Task | A — VPS | B — Managed PaaS | C — Redundant |
|---|:---:|:---:|:---:|
| Initial setup | 🟡 | 🟢 | 🔴 |
| Routine deployment | 🟡 | 🟢 | 🟡 |
| Debugging a production issue | 🔴 | 🟢 | 🟡 |
| Monitoring & alerting | 🔴 | 🟡 | 🟡 |
| Backups & restore | 🔴 | 🟢 | 🟡 |
| Scaling up | 🟡 | 🟢 | 🟡 |
| Security patching | 🔴 | 🟢 | 🟡 |
| Ongoing maintenance | 🔴 | 🟢 | 🔴 |
| **Overall** | **🔴 Complex** | **🟢 Easy** | **🟡 Moderate** |
| **Realistic ops time/month** | **8–15 h** **[E]** | **1–3 h** **[E]** | **6–12 h** **[E]** |

Architecture B costs roughly $20/month more than Architecture A at MVP and gives back something like ten hours a month. If your time is worth anything at all, that is not a close call. **[R]** This is the clearest case in the whole analysis of a slightly more expensive architecture being obviously correct because of what it removes.

Architecture C is rated moderate rather than complex only because the components are individually familiar — but it requires failover drills, replica-lag awareness and rolling-deploy discipline that a solo developer will find genuinely demanding.

---

# 13. Final Decision Matrix

Weights kept as specified. I considered raising Reliability, since subscription entitlement corruption is the failure mode that most damages this specific product — but that risk lives mainly in *application design* (webhook idempotency, reconciliation), which all three architectures share equally. Re-weighting would have measured the wrong thing. **[R]**

| Category | Weight | A — Ultra-Budget | B — Balanced | C — Scalable |
|---|---:|---:|---:|---:|
| Cost | 25% | 10 | 8 | 5 |
| Reliability | 20% | 5 | 8 | 9.5 |
| Scalability | 15% | 6 | 8 | 9.5 |
| Security | 15% | 6 | 8 | 9 |
| Developer Experience | 10% | 6 | 9 | 7 |
| Maintenance | 10% | 4 | 9 | 6 |
| Vendor Lock-in | 5% | 10 | 7 | 7 |
| **Weighted score** | | **6.80** | **8.15** | **7.58** |
| **Rank** | | 3 | **1** | 2 |

Scoring notes: A wins Cost and Lock-in outright and loses everything else — its Reliability score of 5 reflects a genuine single point of failure holding subscription state. B loses two points on Cost and one on Lock-in (the payment provider and, to a lesser extent, the video provider) and scores well everywhere else. C is the most reliable and scalable and the most expensive in both money and attention; at Scenario 1 and 2 volumes it is over-engineered, which is what drags its weighted score below B.

**The ranking is scenario-dependent and that matters.** Re-run this matrix at Scenario 3 and C overtakes B, because Reliability and Scalability scores start reflecting revenue actually at risk. The recommendation below is therefore a recommendation *for now*, with a defined trigger to move.

---

# 14. Final Recommendation

## 🏆 Recommended Solution — Architecture B, Balanced Production

**Architecture:** a single server-rendered application plus a separate worker process on a managed container platform, with managed Postgres, managed video, and object storage. One region (Frankfurt). No Kubernetes, no microservices, no multi-region.

**Providers:**

| Layer | Choice | MVP cost **[E]** |
|---|---|---:|
| App + worker | Render (Frankfurt) | $14 |
| Database | Neon PostgreSQL (EU) | $15 |
| Video | Mux — basic quality, 720p cap | $9 |
| Object storage | Cloudflare R2 | $0 |
| Cache/queue | Upstash Redis | $0 |
| Transcription | Deepgram Nova-3 batch | $5 |
| Email | Resend → Amazon SES later | $0 |
| Edge/DNS/WAF | Cloudflare (free) | $0 |
| Errors/uptime | Sentry free + UptimeRobot | $0 |
| CI/CD | GitHub Actions | $0 |
| Payments | Paddle (MoR) — or Stripe if jurisdiction allows | ~5% of revenue |
| | **Total** | **~$62/mo** |

**Expected cost at larger scale [E]:** ~$312/month at 1,000 users; ~$469/month at 10,000 users *with video migrated to per-GB pricing*, or ~$1,534/month if you stay on per-minute video.

**Main advantages**
- Every high-complexity subsystem — transcoding, ABR, CDN, tax compliance, database backups — is somebody else's operational problem.
- Cost is predictable enough to forecast, and dominated by a single variable (video minutes) that you can measure and control.
- Video delivery, the largest cost line, is migratable — provided you hold your own source masters.
- Scales to roughly 10,000 users without an architectural change: bigger instances, a second replica, a read replica.
- One or two people can run it with an hour or two of ops per month.

**Main disadvantages**
- Roughly $20/month more than the bare-metal alternative at MVP, and ~$250/month more at Scenario 3.
- Multiple vendors means multiple invoices, multiple status pages and multiple failure domains to understand.
- Per-service pricing punishes service proliferation: resist the urge to split the monolith.
- Metered database compute needs watching; it is the one line that can drift upward quietly.

**Biggest risks**
1. **Video cost overrun.** A viral course, autoplay previews, or an uncapped 1080p ladder can multiply the largest line item within one billing cycle. *Mitigate:* cap `max_resolution=720p`, `preload="none"`, lazy-load players, one player per page, and a weekly delivered-minutes alert.
2. **Payment-provider jurisdiction.** If §1.4 is resolved late, billing, entitlement and admin tooling all get rewritten. *Mitigate:* decide before writing billing code.
3. **Entitlement drift.** Missed or duplicated webhooks corrupt access silently and are discovered by angry customers. *Mitigate:* signature verification, idempotency by event ID, a nightly reconciliation job, and admin diagnostics — all already in the brainstorm's MVP scope.
4. **Video vendor lock-in.** If you never keep source masters, migrating means re-collecting content from instructors. *Mitigate:* every upload lands in R2 first, then is pushed to the video provider.
5. **Transcription pipeline fragility.** Silent failures produce published lessons with no subtitles. *Mitigate:* explicit states, retry limits, a dead-letter queue, and an admin view of stuck jobs.
6. **Provider price movement.** Demonstrated live by Hetzner's June 2026 increases **[V]**. *Mitigate:* keep everything containerised and portable; avoid long prepayments on volatile lines.

**Migration strategy**
- **Into it:** deploy Stage 1 as described; there is nothing to migrate from.
- **Within it:** each component is independently swappable behind a thin interface. Database moves by dump/restore; storage by `rclone`; video by re-upload from your own masters; email and STT by changing one adapter.
- **Out of it:** the app is a container and the data is plain Postgres. Moving the entire stack to a Hetzner box, or to AWS, is a matter of days rather than a rewrite — as long as the six rules in §10.2 are honoured.

**Why this fits this platform specifically**
- The brainstorm's own strategy is "use managed services and focus on product-market fit". This architecture is the literal implementation of that sentence.
- A **curated** catalogue means content volume is bounded and predictable, which makes per-minute video pricing safe at MVP and makes transcription a rounding error rather than a risk.
- **Audio-only lessons** — explicitly planned — bill at one tenth of video rates on the recommended provider, a structural saving that generic advice would miss.
- The riskiest part of the product is **entitlement correctness**, not throughput. This architecture puts the database, the webhook receiver and the worker on managed infrastructure so your attention goes to that logic instead of to disk-space alerts.
- **Subtitles are a learning feature, not just accessibility.** Decoupling transcription from the video vendor and storing timed segments in Postgres keeps interactive transcripts, dual subtitles and translated captions all reachable later without re-processing.

---

### 💰 Cheapest Viable Option

**Architecture A — one Hetzner VPS, ~$41/month at MVP.**

Genuinely viable for production, not a toy: a €8.49 CX33 runs the app, worker, Postgres and Redis comfortably for 100–500 users, with video and object storage external. To count as production-ready it needs automated encrypted offsite backups with a tested restore, uptime alerting to your phone, a firewall, and origin IP hidden behind Cloudflare. Choose it if cash is genuinely the binding constraint or if you positively enjoy operations. Understand that you are buying roughly $20/month of savings with roughly ten hours a month of your own time and a real single point of failure holding your subscribers' billing state.

### ⚖️ Best Value Option

**Architecture B — the recommended stack, ~$62/month at MVP.**

The best balance of cost, reliability and complexity for a platform at this stage, and the highest weighted score in §13. It removes almost all operational work at a price difference that is immaterial next to your payment-processing fees, and it scales to ~10,000 users without an architectural rewrite.

### 🚀 Long-Term Option

**Architecture C — redundant app tier, HA database, per-GB video, ~$655/month at Scenario 3.**

Correct once downtime costs more than redundancy — roughly when recurring revenue makes an hour offline more expensive than the ~$185/month premium over Architecture B. Move to it deliberately, triggered by measured pain, not by anticipation. Even here the answer is not Kubernetes: two app nodes behind a load balancer, a standby database and an autoscaled worker pool cover everything this platform will need well past 10,000 users.

---

# 15. Research Quality Notes

**What is verified [V].** All pricing marked [V] was checked in August 2026 against official pricing pages or official documentation, linked inline: Mux, Cloudflare Stream, Cloudflare R2, Bunny Stream, Hetzner's published price list, Render, Railway, Vercel, DigitalOcean, Upstash, Backblaze B2, and vendor documentation for Paddle, Polar and Lemon Squeezy. Where a figure came from a reputable secondary analysis rather than a vendor page — Neon's post-acquisition rates, Sentry's tier pricing, Render's April 2026 workspace change, speech-to-text rates — the source is linked and the figure cross-checked against at least one other source.

**What is estimated [E].** Every monthly total, every scenario cost and every migration threshold. These are arithmetic on [V] rates plus the [A] usage assumptions in §1.3.

**What is assumed [A].** Catalogue size, watch time per active user, blended bitrate, storage-per-minute for ABR ladders, EUR/USD conversion, email volume, and the geographic split of your audience. **These are the inputs most likely to be wrong, and the ones with the largest effect on the answer.** If your learners watch 45 minutes a day rather than 15, every video figure triples.

**What is recommendation [R].** Provider selection, architecture ranking, the decision to skip DRM and search infrastructure at MVP, the operational-time estimates, and the argument that Architecture B beats Architecture A.

**Known gaps, stated honestly.**
- Paddle's current fee schedule was not verified from its pricing page in this pass; ~5% + fixed fee is an [A] and should be confirmed directly, because at MVP it is your largest single cost.
- Moroccan data-protection filing requirements are flagged as [A] and need local legal advice, not an engineering opinion.
- Mux's "basic" encoding ladder is judged visually adequate for low-motion instructional video **[R]** — validate this with a real lesson before committing the catalogue.
- Hetzner's included traffic allowance was not re-verified against the post-June-2026 terms; confirm before relying on it for Architecture A.
- Bunny's storage-per-minute figure for an ABR ladder is an [A]; measure it on real content before modelling Scenario 3 seriously.

**A standing caution.** Three of the most decision-relevant facts in this document — Hetzner's price rise, Render's workspace restructure, and Neon's post-acquisition price cuts — all happened within the last twelve months. Treat this document as a snapshot with a shelf life of roughly one quarter, and re-verify anything you are about to sign for.

---

# 16. Next Phase

This document deliberately contains no implementation steps, no infrastructure code and no deployment tutorial.

**Two decisions are needed before implementation can start:**

1. **Payment provider and operating jurisdiction** (§1.4). This determines the billing integration, the entitlement sync model and the admin tooling.
2. **Confirm or correct the usage assumptions in §1.3**, particularly catalogue hours and watch time per active user. Everything downstream is arithmetic on those two numbers.

**One decision can be deferred but should be made consciously:** Mux versus Cloudflare Stream for MVP video (§8.3). The cost difference at MVP is roughly $19/month; the difference in analytics and audio-only economics is larger than the price gap.

Once the architecture is approved, the implementation phase covers provisioning, environment and secrets setup, CI/CD, database migration workflow, the video upload and transcription pipeline, webhook handling and reconciliation, monitoring and alerting, and the backup and restore runbook.
