# ADR-015 — M6 transcription: what implementation settled

**Status:** Accepted
**Date:** 2026-08-21
**Companion to:** ADR-014 (decisions taken before code).

---

## 1. Editing un-approves, and clears the signature

**Decision.** Editing any segment of an `APPROVED` transcript returns it to
`IN_REVIEW` **and** nulls `reviewed_by` and `approved_at`.

**Why it is in the editing task rather than the review one.** It is a property
of editing. An approval describes the words that were approved; changing them
afterwards leaves an approval standing over content nobody signed off, which
is unreviewed subtitles wearing an approval — the thing ADR-014 §3 keeps from
learners, arriving from inside. Deferring it by one task would have shipped
that window.

**Why the signature must be cleared and not only the status.** A row that kept
`reviewed_by` would go on naming somebody as having approved words they never
saw. **The database cannot catch this**: `approved_transcript_is_signed` only
requires a signature *when* the status is `APPROVED`, so a row that is
`IN_REVIEW` with a stale reviewer is perfectly legal. This is a decision the
schema cannot make, which is exactly why it is written down.

---

## 2. What the review step actually buys

**Decision.** `MACHINE → IN_REVIEW → APPROVED`, with no direct move from
`MACHINE`.

**Stated honestly:** it prevents approving a transcript **nobody has opened** —
a bulk stamp over raw machine output. It does **not** prevent approving one
nobody has *read*. A reviewer determined to click twice still can.

The stronger guarantee is per-segment sign-off, which is a product decision
about reviewer effort rather than a correctness one. Recorded here so that
"the review step protects learners" is not read as more than it is.

**An empty transcript cannot be approved.** An approved transcript with no
cues renders an empty subtitle file, which a player advertises as "subtitles
available" and then shows nothing — worse than having none, because it looks
provided.

---

## 3. VTT escaping has a second-order case

**Decision.** Cue text is escaped for `&`, `<` and `>`, in that order, and
that is also what neutralises the cue separator.

**The obvious half.** A transcript is user-supplied content rendered into a
file a browser parses. CLAUDE.md §6 bans `dangerouslySetInnerHTML`; this is
the same rule arriving through a file instead of a component.

**The half worth writing down.** `-->` is the cue separator, and a lesson
about arrows or about code contains it legitimately — so it is a *content*
problem before it is an attack. It survives naive escaping because neither `-`
nor `>` alone is reserved. Escaping `>` to `&gt;` breaks it up, so the
separator is handled **by** the escaping rather than beside it. Left alone it
ends the cue early and every subtitle after that point is lost.

**Ordering is load-bearing.** `&` must be escaped first, or `&lt;` becomes
`&amp;lt;` and the learner reads the escape.

---

## 4. Cache invalidation is by content, not by purging

**Decision.** The rendered VTT is cached under a key carrying the transcript's
`updated_at`, and the ETag carries the same version. Editing a segment touches
the transcript.

**Why the touch is necessary.** Editing a segment does not otherwise modify
the transcript row, so the key would not move and the cache would serve the
words a reviewer had just corrected.

**Why invalidation by content is the right shape.** A purge has to be
remembered by every writer that appears later; a version in the key is
remembered by nobody and works anyway. The TTL becomes a size bound rather
than a correctness one — a stale entry is unreachable, not wrong.

**`Cache-Control: private`.** Subtitles are gated content, and a shared cache
holding them would serve one learner's entitlement to the next request. The
cost is that subtitles get no CDN benefit, which is the point at which
ADR-014 §2's Redis-over-R2 decision would be revisited.

---

## 5. A shared idempotency table needs namespaced providers

**Decision.** `WebhookEvent.provider` is written as `video:<name>` and
`transcription:<name>`. M5's receiver was changed to match.

**The collision this prevents.** Both fakes are called `fake`, and the table
is unique on `(provider, provider_event_id)`. Writing the bare name puts two
providers' events in one namespace, so a single id collision discards one
provider's event as a duplicate of the other's — **answering 200 while doing
nothing**, with the symptom being a lesson that never gets subtitles.

**M8 must use `billing:`.** The convention is enforced by nothing but two
`namespaced()` helpers, one per app. That duplication is honest but it is
also the way the next app forgets.

---

## 6. Fixes to earlier milestones, found here

**M5's playback token was flaky one run in eight.** The token was
`base64(payload + b"." + signature)` and verification split the decoded bytes
on the last `b"."` — but an HMAC digest is 32 arbitrary bytes, any of which
can be `0x2E`, an ASCII dot. `pytest-randomly` reseeds each run, so it
presented as a test-ordering problem, which is the wrong thing to go looking
for. Each half is now base64url-encoded before joining, so the separator is
impossible in what it separates. Guarded by 200 round trips rather than one,
because a single round trip passes seven times in eight.

**A 500 for a client mistake.** An invalid cue span reached the database and
the `IntegrityError` reached the client — telling a reviewer who dragged a
handle too far that the server broke. Validated at the boundary now, on the
*merged* values rather than the payload, since a request sending only
`start_ms` can push it past an end it never mentioned. The constraint stays,
because it is the thing that is actually true.

---

## 7. What M6 did not do

- **No real Deepgram adapter.** ADR-014 §1. The integration is unproven; what
  is proven is everything around it.
- **No translations.** `kind` is modelled and only `TARGET` is produced.
- **No notification when a transcript is ready to review.** An instructor must
  look. Same gap M5 left for failed assets; both belong with M11.
- **No word-level timing.** Segment-level only.
- **No per-segment sign-off** — see §2.
