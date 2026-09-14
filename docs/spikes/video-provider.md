# Spike — Integrating a real video provider

**Date:** 2026-09-14
**Status:** research and plan. **Decides nothing** — a video provider is a §5
gate (a new paid service), and §10's milestone order is the owner's.
**For:** the `fake_video` provider M5 shipped deliberately, and the storage that
comes with replacing it

---

## 1. More exists than the milestone list suggests

M5 built the whole pipeline against a fake, on purpose (ADR-012 §1). What is
already in place:

| Piece | State |
|---|---|
| `VideoProvider` protocol — **five methods** | Written before any vendor code |
| Upload → task → provider → webhook → `READY` | Built and tested |
| `MediaAsset` `CheckConstraint` refusing `://` in id columns | Invariant 7, enforced in the database |
| `NEXT_PUBLIC_PLAYBACK_URL_TEMPLATE` with `{playback_id}`/`{token}` | Already read by `LessonPlayer` |
| `CSP_MEDIA_SRC` | Already read by `next.config.ts` |

The frontend and the CSP were plumbed for this in advance. **Integration is
five methods and configuration, not a feature.**

---

## 2. The seam the interface promises does not exist yet

`providers/video.py` says swapping a provider is *"one file"*. **It is not**,
today. The factory lives inside the fake's own module and three call sites
import it from there:

```
apps/media_assets/services.py:27
apps/media_assets/tasks.py:30
apps/media_assets/webhooks.py:36
```

Transcription has the identical shape (`tasks.py:35`, `webhooks.py:32`).

So a swap currently means editing every import site, and **the failure of
missing one is the worst available**: some paths use the real provider and
others the fake, with nothing raising. A settings-driven factory with the fake
as default fixes it, needs no account, and is a prerequisite whichever provider
wins.

---

## 3. Mux, on two grounds that are not price

**It closes ADR-013 §6.** Mux signs `mux-signature: t=<unix>,v1=<hmac-sha256>`
with a five-minute default tolerance. That is the timestamped signature M5
recorded as missing and told M8 to add:

> Our scheme accepts a valid old signature indefinitely… Real providers bound
> this with a timestamp, and **M8's adapter must add it.**

Both Mux and Paddle — the payment recommendation in
`payment-provider-morocco.md` — sign timestamp-plus-body with a tolerance. That
obligation is satisfied by provider choice rather than by custom work, in both
places.

**Signed playback maps onto `PlaybackToken` exactly**: an RS256 JWT carrying
`sub` (the playback id), `aud: "v"`, `exp`, and `kid`. Our dataclass already
carries token, playback id and expiry, and composes no URL — which is what
invariant 7 requires.

---

## 4. Storage is two copies, and the second one was missed

**Invariant 7 keeps a master in R2 and a derived copy at the provider.** Cost
analyses of "video" in this repository have consistently priced the second and
not the first — ADR-002 §4.1's table is provider delivery and storage, and
`deployment-strategy.md`'s object-storage row is labelled **non-video**.

### 4.1 The master

R2 is $0.015/GB-month with 10 GB free and **no egress charge at any volume**.
The variable is master bitrate, which nobody here has measured — so this is a
formula, not a number. A 60-hour catalogue is 3,600 minutes.

| Master quality | MB/min **[E]** | Total | R2/month |
|---|---:|---:|---:|
| ~4 Mbps, 720p | 30 | 108 GB | **$1.47** |
| ~8 Mbps, 1080p | 60 | 216 GB | **$3.09** |
| ~12 Mbps, 1080p high | 90 | 324 GB | **$4.71** |

For calibration, this repository's own working figures are ~40 MB/min for an
encoded ladder and ~20 MB/min blended delivery; a master sits above both.

`MEDIA_MAX_UPLOAD_BYTES` defaults to **5 GB** — about 83 minutes at 60 MB/min.
Fine for lessons, worth knowing before somebody uploads a masterclass.

### 4.2 The derived copy

Verified against Mux's pricing page: storage **$0.0024/min** at 720p, delivery
**$0.0008/min after 100,000 free delivered minutes a month**.

At a 60-hour catalogue: 3,600 × $0.0024 = **$8.64/month**, with Scenario 1's
~10,000 delivered minutes falling inside the free allowance. **ADR-002 §5's $9
figure verifies**, and so does its ~$29 at Scenario 2.

### 4.3 So video storage is ~$10–13/month, not $9

| Copy | Monthly |
|---|---:|
| Master, R2 | $1.50 – $4.70 |
| Derived, Mux | $8.64 |
| **Total** | **~$10 – $13** |

### 4.4 Masters are the only line that never comes down

Delivery scales with traffic and can fall. Provider storage falls when a course
is deleted. **Masters only accumulate**, because they exist precisely so a
migration is a re-upload script rather than an email to every instructor.

Small now; the line to watch over years rather than months.

### 4.5 Infrequent Access: analysed, and declined for now

Masters are genuinely cold — read once on ingest, then only on a migration.

| | Standard | Infrequent Access |
|---|---|---|
| Storage | $0.015/GB-mo | **$0.01/GB-mo** |
| Retrieval | — | **$0.01/GB** |
| Free tier | 10 GB | **Does not apply** |
| Minimum duration | — | 30 days |

At 216 GB that saves ~$1.08/month, gives up $0.15 of free tier, and costs
~$2.16 on the single migration the masters exist for. **Roughly break-even, so
not worth the complexity.**

**Trigger to revisit: masters past ~1 TB.**

### 4.6 It sharpens the R2-direct option

Serving progressive MP4 straight from R2 means **one copy, not two** — no
provider storage line at all.

| | Storage | Delivery | Total |
|---|---:|---:|---:|
| R2 master + Mux | $3.09 | $0 | **~$12/mo** |
| R2 only | $3.09 | $0 (egress free) | **~$3/mo** |

Four times cheaper, bought at the price of adaptive bitrate — which matters for
EU and MENA learners substantially on mobile. `infra/docs/provisioning.md` §4
has the full argument; the correction here is that the gap is wider than that
section states, because it priced Mux without the master beside it.

---

## 5. The build

| | Task | Needs an account? |
|---|---|---|
| T1 | Provider selection seam; fake stays the default | **No** |
| T2 | The adapter — five methods | No, to write |
| T3 | RS256 signing dependency (`PyJWT` + `cryptography`, or the vendor SDK inside the adapter) — **§5 gate** | No |
| T4 | Short-lived presigned R2 `GET` so the provider can pull the master | No |
| T5 | Recorded webhook fixtures against the real handler — §6 forbids mocking our own layer | **Yes** |
| T6 | Config: `CSP_MEDIA_SRC`, playback URL template | No |
| T7 | End to end — upload a real lesson, watch it play | **Yes** |

**T1–T4 and T6 are buildable today.** Only proving it works needs the account.

---

## 6. Sequence it after the first deploy, not before

The pipeline has never run. No event has reached Sentry. The rollback runbook is
half-rehearsed. **Adding an unproven provider to an unproven deployment means
that when something breaks, you do not know which half broke.**

Deploy what exists, prove the pipeline, then add video as a change that can be
rolled back. The money agrees: video is the one line with a real bill, and it
costs nothing while there are no learners.

---

## 7. What could not be verified

| Unknown | Why it matters |
|---|---|
| **Mux's Free plan caps at 10 videos** | Not viable for a catalogue — Pay-As-You-Go is required |
| **Pay-As-You-Go advertises a "$20 monthly usage credit"** | If recurring, Mux is effectively **$0/month** at Scenario 1. Not asserted here — this is the class of fact §6 forbids inventing, and it is one email to confirm |
| Master bitrate | Nobody has measured one. §4.1 is a formula for that reason |
| Whether R2 versioning or a second copy protects the masters | **M14 spec §4.4** — T8 was widened for this on the same day |

---

## 8. What this leaves open

A provider is a **§5 gate**: a new paid service and a change to the monthly
bill. The dependency in T3 is a second §5 gate. And M5 is closed, so where this
work sits — a new milestone, or tasks appended to an existing one — is §10's
question and the owner's.

**Nothing here should be started beyond T1**, which is a correctness fix to a
seam this repository already documents as existing.

---

## Sources

- [Mux — verify webhook signatures](https://www.mux.com/docs/core/verify-webhook-signatures)
- [Mux — secure video playback](https://www.mux.com/docs/guides/secure-video-playback)
- [Mux — video pricing](https://www.mux.com/pricing/video)
- [Cloudflare R2 — pricing](https://developers.cloudflare.com/r2/pricing/)
