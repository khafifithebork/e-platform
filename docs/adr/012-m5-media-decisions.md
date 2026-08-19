# ADR-012 — M5 media pipeline: what we build against, and what we defer

**Status:** Accepted
**Date:** 2026-08-19
**Context:** M5 — Media Pipeline. The first milestone with a bill attached, so
CLAUDE.md §5 (new paid service, new dependency) and §2 (read the deployment
documents before touching provider adapters) both applied before any code.

---

## 1. M5 spends nothing

**Decision.** The milestone ships with **zero external spend**. Wiring a real
video provider is a separate task, gated on approval of the bill.

**Why this works for storage but not video.** M4 proved that a fake provider
lets a system be built and tested before the real one is chosen. The two
providers here are not equally fakeable:

- **Storage.** R2 is S3-compatible and so is **MinIO**, which runs in
  `docker-compose` for free. So the storage adapter is **real code** — genuine
  presigned PUTs, genuine signature validation — pointed at a local container.
  Production changes environment variables, not code. A *fake* storage adapter
  would have been actively misleading, because presigned uploads are precisely
  the thing that goes wrong: a fake would happily accept a request that R2
  rejects.
- **Video.** No local equivalent exists. So the documented interface
  (`create_asset`, `get_playback_token`, `delete_asset`) plus a
  `FakeVideoProvider`, exactly as M4 did for billing.

**Consequence, stated honestly.** The Mux integration is *unproven* at the end
of M5. What M5 proves is that everything around it is correct and that
swapping the adapter is a one-file change. That is the same trade M4 made with
billing, and the same residual risk.

**`architecture.md` §10 M5 asks for the interface before the vendor code**, so
this ordering follows the document rather than departing from it.

---

## 2. Three dependency decisions

**`boto3` — accepted.** Presigned URL generation and object verification
against any S3-compatible store. The alternative is hand-rolling SigV4
signing, which is a security-critical wheel nobody should reinvent.

**MinIO — accepted, dev and CI only.** A container, not a Python package, so
it has no production footprint. The alternative is testing against real R2,
which means a bill and live credentials in CI.

**`python-magic` — rejected.** File-type verification reads the first bytes
ourselves, roughly twenty lines for the four signatures we accept. The library
needs `libmagic`, a system dependency that complicates Windows and CI, and its
generality buys nothing when the accept-list is short. §7 requires checking
magic bytes rather than the extension; it does not require a library to do it.

---

## 3. One `WebhookEvent` table, in `core`

**Decision.** A single table with `UniqueConstraint(provider,
provider_event_id)`, shared by the media provider in M5 and the payment
provider in M8.

**Why.** Invariant 8 is a *discipline* — verify signature, insert, enqueue,
return 200, no business logic in the handler — and the point of writing it
once is that there is one place to get it right. Two tables mean two handlers
and two chances to reorder those steps, and the failure mode is silent: a
provider retry double-processes and somebody's subscription is extended twice
or an asset is transcoded twice.

**Consequence.** `core` gains a concrete model. ADR-003 said M1 ships none;
that was about M1's ordering relative to the custom `User`, not a permanent
rule, and the constraint it protected (User first) has long since been
satisfied.

---

## 4. The resolver stays `Lesson`-shaped — deliberately, against a recommendation

**Decision.** `resolve_access(user, lesson)` keeps its signature in M5.

**The recommendation it declines.** ADR-002 §7.5 item 2 says to keep the
resolver "generic over gated content, not specifically `Lesson`", so that a
live session, a booked call and a downloadable resource are later just things
with an access decision.

**Why not now.** In M5 every gated thing is still a lesson — a `MediaAsset`
hangs off one, and playback is authorised through its lesson. Generalising
today produces an abstraction with a single implementor, designed against a
second case nobody has specified: live classes are CLAUDE.md §11 decision 5,
still open, and a `GatedContent` protocol invented before that decision would
most likely be the wrong shape and would still need changing.

**What makes this safe to defer.** The generalisation is additive. The rules
live in `resolve_account_access`, which never touches a lesson at all; only
the preview and course-owner branches are lesson-specific. A second content
type needs a second thin entry point beside `resolve_access`, not a rewrite.

**Recorded so it is a decision, not an oversight.** Anyone finding the
mismatch between ADR-002 and the code should find this section rather than
assume the document was missed. Revisit when the second gated type actually
exists — which is also when the abstraction can be validated instead of
guessed.

---

## 5. What this means for M8 and beyond

- **M8 inherits the webhook table and its discipline**, already exercised by a
  real handler with real replay tests. Billing webhooks become a second
  provider on a proven path.
- **The video provider swap is one file.** If Mux is expensive at the volumes
  ADR-002 §5 models, migration is a re-upload script reading masters from R2 —
  because R2 holds the master and the provider holds a derived copy
  (invariant 7).
- **ADR-011 applies immediately in M5.** `MediaAsset.status` will start
  deciding whether a playback token is minted. Every path that can write it
  needs the write-permission audit in the same change that gives it that
  meaning.
