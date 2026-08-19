# M5 — Media Pipeline

**Status:** Approved 2026-08-19. Branch `feat/m5-media-pipeline`. T1 done.
CLAUDE.md §5 gates new dependencies and anything that alters the monthly bill;
§2 requires reading `deployment-strategy.md` and ADR-002 before touching
provider adapters. Both apply here — M5 is the first milestone with a bill
attached.

Sources: `architecture.md` §3.5 (the upload sequence), §5.2 (provider +
`provider_asset_id`), §6.2, §7 (threat model, file uploads), §10 M5;
ADR-002 §7.5 (stack changes that keep streaming cheap).

---

## 1. Objective

An instructor uploads a video; it becomes playable, gated by the M4 resolver,
with visible processing status and a real failure path.

Invariant 6 is the shape of the whole milestone: **media never passes through
Django.** Uploads go browser → storage via presigned PUT. Playback goes
browser → CDN via a signed token. Django handles JSON, never bytes.

---

## 2. Decisions — all four settled, 2026-08-19

| # | Decision | Outcome |
|---|---|---|
| 2.1 | External spend in M5 | **None.** Real S3 against MinIO; fake video provider. |
| 2.2 | New dependencies | **Approved:** `boto3`, MinIO container (dev only), hand-rolled magic bytes. |
| 2.3 | `WebhookEvent` table | **One, shared, in `core`.** |
| 2.4 | Resolver shape | **Stays `Lesson`-shaped.** Recorded in ADR-012 §4. |

Recorded in `docs/adr/012-m5-media-decisions.md`.

### 2.1 Do we pay for anything in M5? — **settled: no**

M4's fake billing provider worked: the whole entitlement system was built and
tested before a payment provider existed, and M8 becomes a swap. The same
split applies here, but the two providers are **not** equally fakeable.

- **Storage (R2).** R2 is S3-compatible, and so is **MinIO**, which runs in
  `docker-compose` for free. So the storage adapter can be *real* code —
  actual presigned PUTs, actual signature validation — pointed at a local
  container. Production changes environment variables, not code. A fake here
  would prove nothing, because presigned uploads are exactly the thing that
  goes wrong.
- **Video (Mux).** Not fakeable in the same way and not locally substitutable.
  So: the provider interface plus a `FakeVideoProvider`, exactly as M4 did
  with billing.

**Recommendation:** M5 ships with **zero external spend**. Real S3 code against
MinIO; a fake video provider behind the documented interface. Wiring the real
Mux adapter becomes its own task, gated on your approval of the bill, and
touches one file by construction.

**This needs your approval anyway**, because it adds a container to
`docker-compose` and two Python dependencies (below).

### 2.2 New dependencies — **approved as listed**

| Dependency | Why | Alternative considered |
|---|---|---|
| `boto3` | Presigned PUT generation and object verification against any S3-compatible store. The only realistic client. | Hand-rolled SigV4 signing — a security-critical wheel nobody should reinvent. |
| `minio` (container, dev only) | An S3 API to test against without a bill. Not a Python package; no production footprint. | Testing against real R2, which means a bill and credentials in CI. |
| *(none for file typing)* | Magic-byte checks are ~20 lines reading the first bytes ourselves. | `python-magic` needs `libmagic`, which is awkward on Windows and adds a system dependency for four signatures. |

### 2.3 One `WebhookEvent` table or one per provider? — **settled: one, in `core`**

Invariant 8 requires an idempotency table unique on `provider_event_id`. M5
needs it for the video provider; M8 needs it for billing. One table with
`UniqueConstraint(provider, provider_event_id)` serves both and means the
handler discipline is written once. Two tables mean two chances to get
"insert first, then process" wrong.

### 2.4 Does M5 keep the resolver `Lesson`-shaped? — **settled: yes, for now**

ADR-002 §7.5 item 2 says to keep the resolver "generic over gated content, not
specifically `Lesson`", so that live sessions and downloadable resources are
later just things with an access decision. M4 built `resolve_access(user,
lesson)`.

**This is a documented recommendation the code does not currently follow, and
I am flagging it rather than quietly changing it.** In M5 every gated thing is
still a lesson — a `MediaAsset` hangs off one — so generalising now would be
an abstraction with a single implementor, and the second implementor (live
classes) is CLAUDE.md §11 decision 5, still open. My recommendation is to
generalise when the second type actually arrives, and to record that in an
ADR so it is a decision rather than an oversight.

---

## 3. Model sketch

**`MediaAsset`** (§5.2), one per lesson: `lesson` (FK, unique),
`source_object_key`, `source_bytes`, `source_checksum`, `provider`,
`provider_asset_id`, `provider_playback_id`, `duration_seconds`, `status`,
`error_message`, `retry_count`.

Status: `PENDING → UPLOADED → TRANSCODING → READY`, with `FAILED` reachable
from any of them.

**Invariant 7, restated because it is the point:** store `provider` and
`provider_asset_id`. **Never a playback URL.** A stored URL means switching
provider is a data migration across every lesson plus a hunt through the
codebase.

**`WebhookEvent`** in `core`: `provider`, `provider_event_id` (unique
together), `event_type`, `payload`, `received_at`, `processed_at`.

---

## 4. The failure path is a deliverable, not an afterthought

§10 M5 names "no dead-letter queue, so failures vanish silently" as the
common mistake. Celery has no DLQ of its own, so:

- Tasks retry with exponential backoff and a bounded `max_retries`.
- On final failure the asset goes to `FAILED` with `error_message` and
  `retry_count` **in the database** — that is the dead-letter queue, and it is
  queryable, visible in admin, and countable for the business alert
  `architecture.md` §4.3 asks for.
- A failed asset must be **retryable** without re-uploading, because the
  master is already in storage.

---

## 5. Abuse cases — these become the first tests

1. An instructor requests an upload URL for **someone else's lesson** → 404.
2. A presigned URL is scoped: wrong content-type, or a file larger than the
   declared size, is **rejected by the store**, not by us being polite.
3. The object key is **server-generated and random** — a user-supplied
   filename never reaches storage (§7: path traversal, overwrite of another
   asset).
4. `complete/` is called for an object that **was never uploaded** → refused,
   and the asset does not advance.
5. The uploaded bytes are **not the declared type** (an `.mp4` that is a PHP
   script) → rejected on magic bytes, not extension.
6. A **playback token is not minted on entitlement denial** — and the test
   asserts the provider adapter was **never called**, since absence of a
   token in the response is weaker than absence of the side effect (§10 M5).
7. A **replayed webhook** changes nothing the second time (invariant 8).
8. A webhook with a **bad signature** is refused before any processing.
9. A webhook for an **unknown asset** does not create one.
10. `provider_playback_id` **never appears** in any response a non-entitled
    caller can read.
11. No response anywhere contains a **playback URL** (invariant 7) — asserted
    against raw bytes.

---

## 6. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR for §2 decisions | approval |
| T2 | `MediaAsset` + `WebhookEvent` models and constraints | T1 |
| T3 | Storage adapter (real S3) + MinIO in compose | T1 |
| T4 | `upload-url/` and `complete/`, scoped to the owner | T2, T3 |
| T5 | Video provider interface + `FakeVideoProvider` | T2 |
| T6 | Celery task: verify, probe, create asset, retry, DLQ | T3, T5 |
| T7 | Webhook receiver — signature, idempotency, enqueue, 200 | T2, T5 |
| T8 | `playback-token/` — resolver first, then mint | T5, M4 |
| T9 | Processing status surfaced to the instructor; retry path | T6 |
| T10 | Abuse cases, query counts, schema, types, ADRs | all |

---

## 7. Invariants this touches

**6** (media never through Django), **7** (provider + id, never a URL),
**4** (adapters), **8** (webhook discipline), **5** (stateless — no local disk
for uploads), **3** (the resolver gates playback), **10** (scoping), **11**
(database constraints), **14** (migrations), **16** (types).

---

## 8. Not in M5

- **Transcription.** M6, and it owns Deepgram.
- **The real Mux adapter**, pending §2.1.
- **Live streaming.** ADR-002 §7.2; CLAUDE.md §11 decision 5 is still open.
- **Audio-only handling as a distinct path.** `lesson_type` already
  distinguishes it (M3); the pipeline treats both as assets until M6 gives
  audio a reason to differ.
