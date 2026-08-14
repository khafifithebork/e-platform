# ADR-002 — Cost & Reliability Revision, and the Streaming Roadmap

**Supersedes:** cost figures in `phase-1-architecture.md` §3.6 (which contained an arithmetic error — corrected below)
**Status:** Proposed
**Date:** August 2026

---

# 1. Executive Summary

Three findings, in order of importance:

1. **You're optimising the wrong line.** Compute is ~$21 of a ~$50 MVP bill. Driving it to zero saves you $250/year. Payment fees at 1,000 subscribers cost ~$6,000/year and video at Scenario 3 costs ~$10,000/year. Compute is the *third* most valuable thing to optimise, and it's not close.
2. **There is a genuinely cheaper *and* more reliable path**, and it isn't the obvious one. It comes from a property of your product: **the catalogue is curated, so public pages change on publish, not per request.** That means the entire anonymous surface can be static, served from the edge, free and effectively unfailable. Combined with keeping Postgres managed while making compute disposable, you get ~40% lower cost *and* better availability than the Render setup.
3. **Live streaming is far cheaper and less disruptive than you probably assume — for one shape, and expensive and disruptive for another.** Broadcast (one teacher → many students) is nearly free and requires almost no stack change. Interactive WebRTC (1:1 conversation practice) requires real architectural work but is astonishingly cheap for *audio-only*, which happens to be exactly what language learning needs.

**Correction first:** `phase-1-architecture.md` §3.6 quoted a revised MVP cost of ~$83/month. That was wrong — I double-counted. Corrected arithmetic in §2.1. I'd rather flag my own error than have you budget from it.

---

# 2. Where the Money Actually Is

## 2.1 Corrected baseline (Architecture B, Scenario 1)

| Line | Cost |
|---|---:|
| Render — Next.js service | $7 |
| Render — Django service | $7 |
| Render — Celery worker | $7 |
| Neon PostgreSQL | $15 |
| Upstash Redis | $0 (free tier) |
| Cloudflare R2 | $0 (free tier) |
| Mux video | $9 |
| Deepgram (amortised) | $5 |
| Resend, Sentry, Cloudflare | $0 |
| **Total** | **$50/mo** |

(With Cloudflare Stream instead of Mux: $69/mo. My earlier "$83" figure was an error — disregard it.)

## 2.2 Leverage ranking

| Lever | Cost at 1,000 subscribers @ $10/mo | Realistic saving |
|---|---:|---|
| **Payment processing (~5% MoR)** | ~$500/mo | Incorporating in a Stripe-supported jurisdiction: ~2.9% + fee → saves ~$200/mo. **The single biggest lever in the business** |
| **Video delivery** | $29 → $806/mo at S3 | Provider choice + 720p cap + audio mode: 50–90% |
| **Compute + DB** | $36–100/mo | Architecture change: 40–60%, i.e. $15–60/mo |

This ordering is the actual answer to "is there anything cheaper." Yes — but the compute layer is where the least money is. I'll optimise it anyway, because the changes below also improve reliability, which is the part you asked about that actually matters.

---

# 3. Cheaper *and* More Reliable — Four Moves

Cheap and reliable usually trade off. These four don't, and here's why each one is genuinely both.

## Move 1 — Make the public surface static ⭐ the big one

**The insight comes from your product, not from infrastructure.** Your catalogue is *curated*. Courses are admin-approved before publishing. Course pages, the landing page, pricing, and language/level listings change when an admin clicks "approve" — perhaps a few times a week — not on every request.

So don't render them per request. Pre-render them at build time and serve them as static assets, rebuilt by a webhook when a course is published.

**Cheaper:** <cite index="153-1">on both Cloudflare's free and paid plans, requests to static assets are free and unlimited — a request only bills when it invokes a Function.</cite> Your entire anonymous, SEO-relevant, most-likely-to-spike surface costs $0 to serve at any volume.

**More reliable:** a static file cannot throw a 500, cannot exhaust a connection pool, cannot be taken down by a slow database query. If Django is down, your marketing site, catalogue and course pages are still up and still converting. That is a genuine availability improvement, not a cost trick.

**Cost:** you need a rebuild trigger on publish, and course pages are stale for the duration of a build (~1–2 min). For a curated catalogue that's a non-issue. Personalised elements (the "Continue learning" strip, access CTAs) hydrate client-side from `/auth/me/`.

**What this changes in the stack:** Next.js `output` stays hybrid — static for `(marketing)` routes, dynamic for `(app)`. It's a routing-group decision, not a rewrite.

## Move 2 — Move Next.js from a container PaaS to the edge

<cite index="151-1">Cloudflare's Workers Paid plan covers Workers, Pages Functions, KV, Hyperdrive and Durable Objects for a $5/month account minimum, with no additional charges for egress or bandwidth.</cite> <cite index="147-1">That $5 includes 10 million requests and 30 million CPU-milliseconds; overage is $0.30 per million requests and $0.02 per million CPU-ms.</cite> <cite index="146-1">Billing is on active CPU rather than wall-clock, so time spent waiting on your Django API doesn't count</cite> — which is exactly the profile of a BFF that mostly proxies.

**Cheaper:** $5 vs $7, and no egress meter at all versus Render's ~$0.15/GB beyond the allowance.

**More reliable:** an anycast deployment across hundreds of locations has a structurally better availability profile than one container in one Frankfurt datacentre. There is no instance to restart, no cold start, no region to lose.

**The honest cost:** the Next.js-on-Workers adapter (OpenNext) is mature but not identical to running `next start`. Some Node APIs and long-running route handlers are constrained. **Validate this with a spike in M0 before committing** — an hour of work that de-risks the decision.

## Move 3 — Make compute disposable, keep state managed

This is the reasoning that makes self-hosting *safe* rather than reckless.

**Self-hosting disasters are almost always state disasters:** a corrupted Postgres with no tested backup, a disk that filled, an upgrade that ate the data directory. They are rarely "the web server fell over."

In your architecture, the app server holds **no state at all**. Postgres is Neon (managed, PITR). Files are R2. Video is Mux. Sessions are in Postgres. The queue is Redis, which is explicitly disposable by design (§3.4 of the architecture doc).

That makes your app server *cattle*. Losing it means redeploying containers from a Dockerfile, not recovering data. Rebuild time from a snapshot plus Dokploy: on the order of 20 minutes, with zero data loss.

**Cheaper:** one Hetzner CX33 (2 vCPU / 8 GB) at €8.49 (~$10) runs Django + Celery + Redis + Caddy comfortably at Scenario 1–2 — versus $14 for two Render Starter services that are individually smaller.

**Not yet more reliable** — one box is one box. That's Move 4.

<cite index="155-1">Both Coolify and Dokploy install in under five minutes; Dokploy idles at ~0.8 GB RAM against Coolify's ~1.2 GB and has a simpler model for a small number of apps, while Coolify offers a much larger service library.</cite> For three containers, **Dokploy** is the better fit — less surface area to maintain.

## Move 4 — Two cheap boxes beat one expensive one

This is where cheaper and more reliable stop trading off entirely.

<cite index="159-1">A Hetzner load balancer costs $6.41/month.</cite> Two CX33 nodes behind it is ~$27/month total.

| | Render (Scenario 2) | Hetzner 2-node (Scenario 2) |
|---|---:|---:|
| Workspace | $25 | — |
| Web + API + worker | $57 | $20 (2 nodes, all three containers each) |
| Load balancer | included | $6.41 |
| **Redundancy** | **single instance per service** | **N+1 — one node can die** |
| **Total** | **$82** | **$27** |

You get **redundancy Render's default tier doesn't give you, at one third of the price.** To match the redundancy on Render you'd scale each service to two instances: ~$139/month.

**The honest cost:** you own OS patching, Dokploy upgrades, and the load balancer config. Realistically 3–6 hours a month once it's set up. Whether that's a cost or a benefit depends on you — see §6.

---

# 4. Reliability Improvements That Cost Nothing

Worth stating plainly, because they matter more than any of the above: **the failures that will actually hurt this product are application-level, not infrastructure-level.**

| Control | Cost | Prevents |
|---|---|---|
| Never self-host Postgres | $0 (already decided) | The single most common self-hosting catastrophe |
| Webhook idempotency table | $0 | Double-extended subscriptions, corrupted entitlement |
| Nightly entitlement reconciliation | $0 | Silent access drift found weeks later by a customer |
| Dead-letter queue on Celery | $0 | Lessons published with no subtitles, invisibly |
| Container health checks + auto-restart | $0 | Most "the site is down" incidents |
| Cloudflare in front, origin IP hidden | $0 | Direct-to-origin DDoS |
| Static public surface (Move 1) | $0 | App outage becoming a *visible* outage |
| **Quarterly restore drill** | 1 hour | The worst day of your life |

An hour spent on the reconciliation job buys more real reliability than $100/month of redundancy. Redundancy protects against machine failure; reconciliation protects against the failure mode you'll actually hit.

---

# 5. Revised Architecture Options

| | **B — Managed PaaS** | **B-lite — Edge + VPS** ⭐ | **B-HA — Redundant VPS** |
|---|---|---|---|
| Frontend | Render container $7 | Cloudflare Workers $5 | Cloudflare Workers $5 |
| Django + Celery + Redis | Render 2 services $14 | 1× Hetzner CX33 $10 | 2× CX33 + LB $27 |
| Postgres | Neon $15 | Neon $15 | Neon $35 |
| Video (Mux, S1/S2) | $9 | $9 | $29 |
| Transcription | $5 | $5 | $10 |
| Email + errors | $0 | $0 | $46 |
| **Scenario 1 total** | **$50** | **$44** | — |
| **Scenario 2 total** | **~$300** | **~$120** | **~$157** |
| **Redundancy** | none at entry tier | none | **N+1 app tier** |
| **Ops burden** | 🟢 1–3 h/mo | 🟡 3–6 h/mo | 🟡 4–8 h/mo |
| **Public-surface availability** | app-dependent | **edge-static** | **edge-static** |

**B-lite is ~12% cheaper at MVP and ~60% cheaper at Scenario 2**, with a strictly better availability profile for anonymous traffic and an equal one for authenticated traffic. B-HA adds real redundancy for less than Render's non-redundant Scenario 2 bill.

---

# 6. The Decision You Should Actually Make

**Containerise properly and make this a late-binding decision.**

The whole point of Docker + Docker Compose is that "Render or Hetzner" is a *deploy target*, not an architecture. Same Dockerfiles, same Compose file locally, same `render.yaml` *or* Dokploy config. Switching later is an afternoon.

Given that, the tiebreaker is what you want out of this project:

- **You want to ship fastest and never think about a server** → stay on Render (B). $6/month more at MVP.
- **You want to learn DevOps properly and keep costs low** → B-lite. Your own brief asks me to act as your DevOps engineer and Phase 4 is explicitly Docker/Compose/CI-CD/rollback/secrets. You will learn ten times more running Dokploy on Hetzner than clicking deploy on Render, and the portfolio story is meaningfully stronger.

**My recommendation: B-lite**, with the Cloudflare Workers spike validated in M0. It's cheaper, the public surface is more available, and it aligns with what you said you want to learn. Take B if the ops time turns out to compete with shipping.

**One thing that isn't optional either way:** Move 1 (static public surface). It's free, it improves availability, and it's a routing-group decision in Next.js. Do it regardless of hosting.

---

# 7. Streaming

"Streaming features" covers three different things with wildly different costs and stack impact. Taking each.

## 7.1 VOD streaming — what you're already building

Two changes worth making, both product features that happen to cut cost:

**Audio mode.** Language learning genuinely works audio-only — commuting, walking, revision. Mux bills audio-only assets at **one tenth** the 720p video rate across encoding, storage and delivery. Ship a per-lesson "listen only" toggle and you cut delivery cost for every learner who uses it by 90%. Your brainstorm already plans audio-only lessons; this extends it to video lessons as a playback mode.

If 30% of watch time moves to audio mode, Scenario 3 video delivery drops from ~$806 to roughly **$570/month**. A UI toggle that saves $2,800/year and makes the product better for learners.

**Delivery discipline** (from the deployment doc, restated because it's the cheapest money you'll ever save): `max_resolution=720p` on playback URLs, `preload="none"`, lazy-load the player, one player per page, pause on tab-hidden.

**Stack impact: none.** Both are player configuration.

## 7.2 Live broadcast — one teacher, many students

This is the cheap one, and it barely touches your architecture.

Cloudflare Stream Live and Mux Live both accept an RTMPS/SRT push from OBS, transcode to HLS, deliver over CDN, and auto-record the session into a VOD asset. <cite index="18-1">Cloudflare Stream charges $1 per 1,000 minutes delivered and $5 per 1,000 minutes stored regardless of bitrate or resolution, with no charge for ingest or encoding, and provides signed URLs and hotlink prevention for access control.</cite>

**Cost example:** a weekly 60-minute live class with 100 attendees = 6,000 delivered minutes/month = **$6/month**. The recording then becomes a normal lesson.

**Stack impact — genuinely minimal:**
- `Lesson.lesson_type` gains `LIVE_SESSION`.
- `MediaAsset` gains a `live_input_id` and a `scheduled_start_at`.
- Same signed-token endpoint, same entitlement resolver, same player component.
- New: a schedule model and a reminder email. That's it.

Live *chat* during the broadcast is the only thing that adds real complexity — see §7.4.

**This is the live feature to build first**, and it's a Phase 2 feature, not an architectural commitment.

## 7.3 Interactive WebRTC — 1:1 or small-group conversation practice

This is the expensive-in-engineering, cheap-in-bandwidth one. And for a language platform it's the most valuable feature you could eventually add, because *speaking practice* is the thing courses can't deliver.

| Option | Pricing | Notes |
|---|---|---|
| **Cloudflare Realtime SFU** | <cite index="171-1">$0.05 per GB of egress from Cloudflare to clients, with a shared 1,000 GB free tier across SFU and TURN</cite> | Lowest level. You build rooms, presence, roster, recording |
| **Cloudflare RealtimeKit** | <cite index="164-1">$0.002 per participant-minute with video, $0.0005 audio-only; recording/RTMP/HLS export at $0.010 per minute ($0.003 audio-only); no free tier</cite> | SDKs and pre-built UI, meetings/participants/roles, recording, chat, breakout rooms |
| **LiveKit Cloud** | <cite index="165-1">WebRTC participant minutes $0.0004–$0.0005, downstream bandwidth $0.10–$0.12/GB, upstream free; tiers from $50/mo (Ship) to $500/mo (Scale)</cite> | Most mature SDK ecosystem; monthly floor is the catch |

**The number that should change your product thinking:** audio-only conversation practice at $0.0005 per participant-minute means a **30-minute 1:1 speaking session costs $0.03**. A thousand sessions a month costs $30. Cloudflare's 1,000 GB free tier alone covers a very large amount of audio-only traffic.

**Stack impact — this one is real:**
- Scheduling and booking (availability, timezones, cancellations, no-shows) — a substantial domain in its own right.
- Room lifecycle and token minting (fits your entitlement pattern cleanly).
- Presence and signalling — bidirectional, so genuinely needs WebSockets.
- Recording → back into the VOD pipeline, plus consent handling.

**Recommendation: don't build this until you have paying subscribers asking for it.** Your brainstorm correctly excludes speaking practice from MVP. But note that audio-only makes it economically trivial when you do — the constraint is engineering time, not bandwidth cost.

## 7.4 Real-time app features — and the WebSockets trap

Live progress sync, notification badges, "your transcription finished", live chat during a broadcast.

**Use Server-Sent Events, not WebSockets, until you genuinely need bidirectional.** SSE is one HTTP response that stays open. It works through every proxy, needs no new protocol, no sticky sessions, no channel layer, and Django ASGI serves it natively with `StreamingHttpResponse`.

WebSockets means Django Channels, a Redis channel layer, sticky sessions at the load balancer, and a whole new class of connection-lifecycle bugs. Adopt it only when a feature requires the client to *push* — which is live chat and WebRTC signalling, and nothing else on your roadmap.

## 7.5 Stack changes to make *now* so streaming is cheap later

All five cost nothing today:

1. **Run Django under ASGI from day one** — Uvicorn workers under Gunicorn, not plain WSGI. SSE and Channels later become configuration rather than migration. This is a one-line change now and a painful one after M8.
2. **Keep the entitlement resolver generic over "gated content"**, not specifically `Lesson`. A live session, a booked call and a downloadable resource are then all just things with an access decision.
3. **Keep the `MediaAsset` provider abstraction** — live recordings arrive as VOD assets through the same adapter you already built.
4. **Model `lesson_type` as an extensible enum**, not a boolean `is_video`.
5. **Don't adopt WebSockets, Channels, or a booking domain until a shipped feature demands them.** Every one of them is easy to add to a clean ASGI monolith and miserable to retrofit into a WSGI one — which is why item 1 is the only thing you actually need to do now.

**One hosting consequence worth noting:** long-lived connections (SSE, WebSockets) run naturally on a VPS or a container platform and awkwardly on request-scoped serverless. If live features are on your roadmap, that's another modest point in favour of B-lite's Hetzner backend over anything serverless for the Django tier. The Next.js frontend on Workers is unaffected — the connection terminates at Django.

---

# 8. Revised Recommendation

| Decision | Recommendation |
|---|---|
| **Hosting** | **B-lite** — Cloudflare Workers (Next.js) + Hetzner CX33 with Dokploy (Django, Celery, Redis) + Neon Postgres. ~$44/mo. Validate the Workers/OpenNext spike in M0 |
| **Public surface** | **Static-generated, rebuilt on publish.** Do this regardless of hosting choice — free, and it decouples your marketing surface from app availability |
| **Redundancy** | Add the second node + load balancer at Scenario 2 (~$27/mo total). Cheaper than non-redundant Render |
| **Video** | Unchanged: Mux, basic quality, 720p cap. **Add an audio-mode toggle** — a product feature that cuts delivery cost up to 90% for users who choose it |
| **Live broadcast** | Phase 2. Cloudflare Stream Live. ~$6/month for a weekly class of 100. Near-zero architectural impact |
| **Interactive WebRTC** | Phase 3+, only on demand. Audio-only makes it economically trivial; engineering time is the real cost |
| **Real-time features** | SSE over Django ASGI. No WebSockets until live chat or WebRTC signalling exists |
| **Do now, costs nothing** | Run Django under ASGI; keep entitlement generic over gated content; keep the media provider abstraction |

**Everything else in `phase-1-architecture.md` stands** — the domain model, API design, security plan, testing strategy, milestone ordering, and the decision to build entitlements before billing.

---

# 9. Next Milestone

**M0 — Planning & Foundations**, with two additions:

- **Spike: Next.js on Cloudflare Workers** via OpenNext. Timebox to two hours. Deploy a hybrid app with one static route and one dynamic route that proxies to a stub API. If it's smooth, B-lite is confirmed; if it fights you, the Next.js service goes back on Render and everything else in B-lite still holds.
- **Set Django to ASGI** (Gunicorn + Uvicorn workers) in the base configuration, even though nothing needs it yet.

Still blocking: the payment jurisdiction decision.
