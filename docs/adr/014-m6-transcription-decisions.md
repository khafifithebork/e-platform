# ADR-014 — M6 transcription: four decisions, two of which decline a document

**Status:** Accepted
**Date:** 2026-08-20
**Amends:** `architecture.md` §3.1 (see §2) and §10 M6 (see §3).
**Context:** M6 — Transcription & Subtitles. Taken before any code, per
CLAUDE.md §5 and §7.

---

## 1. No spend in M6

**Decision.** The documented transcription interface plus a fake. The real
Deepgram adapter is a separate task, gated on approval of the bill.

**Why the same shape as M4 and M5.** Both proved that a system built against a
fake makes the real provider a swap rather than a rewrite. Deepgram differs
from M5's storage in one way that matters: there is **no free local
equivalent**, so unlike MinIO there is nothing to point real code at. This is
therefore the billing-provider case, not the storage case.

**What the fake must do to be worth having.** Return *realistic* output —
several segments, plausible timings, a confidence score, word boundaries. A
fake returning one segment would let the review workflow and VTT rendering
pass while proving nothing about multi-cue subtitle files, which is the thing
most likely to be wrong.

**Residual risk, stated plainly.** The Deepgram integration is unproven at the
end of M6. What is proven is everything around it.

---

## 2. Rendered VTT is cached in Redis, not written to R2

**Decision.** Render from `TranscriptSegment` rows on demand, cache in Redis,
serve with an `ETag`.

**This declines the §3.1 diagram**, which lists R2 as holding
"masters · resources · VTT".

**Why.** A VTT for an hour of speech is tens of kilobytes and renders with one
query and a string build. Redis is already in the stack and is declared
disposable (§3.4) — a projection is precisely the thing that may be lost.
Writing to R2 adds an upload on every segment edit, a second place a subtitle
can be stale, and an invalidation problem for a file that regenerates in
milliseconds.

The `ETag` matters more than the cache: an edit changes the content, so the
validator changes, and nothing has to remember to purge anything.

**When R2 wins.** When subtitles are served at CDN volume and the origin
request itself is the cost. That is a traffic decision, and there is no
traffic yet.

**Invariant 13 is unaffected either way** — it forbids VTT being the *stored
form*, and under both options the rows remain the source.

---

## 3. Publication is never blocked; unapproved transcripts are never served

**Decision.** M3's `approve()` is untouched. Instead, **the VTT endpoint
serves only `APPROVED` transcripts** — `MACHINE` and `IN_REVIEW` are a 404 to
a learner.

**This amends `architecture.md` §10 M6**, which names a "publish gate
requiring approval" as a deliverable.

**Why the requirement is still met, and better.** §10 M6's reason is that
*"unreviewed subtitles are worse than none for language learning"* — a machine
transcript teaches learners the wrong words with confidence. That is a
statement about **what a learner sees**, not about when a course goes live. So
the control belongs at the point of serving, and putting it there is:

- **Stricter where it counts.** It covers a lesson added to a course that is
  already published, which a gate evaluated at publication time does not.
- **Looser where it does not.** A course whose subtitles are still being typed
  can go live and teach; the video was never the problem.

**What is given up, and accepted.** A published lesson may have no subtitles
for a while, and nothing tells the learner why. That is a gap in
communication rather than in correctness, and it belongs with notifications in
M11.

**The risk to watch.** This decision puts the whole weight of the requirement
on one endpoint. If anything else ever renders segments — an API returning
transcript text for an interactive transcript, a search result, an export —
**it must apply the same `APPROVED` check**, or unreviewed text reaches
learners by a route the gate never covered. That is ADR-011's shape: a status
field acquires meaning, and every reader has to honour it, not just the one
that was written first.

---

## 4. The instructor approves their own transcripts

**Decision.** An instructor may move their own transcript to `APPROVED`.
Admins may too.

**Why this differs from ADR-007 §2**, which settled that only admins publish a
course. Publication is an editorial judgement about whether a course belongs
in the catalogue. Approving a transcript is a **language** judgement about
one's own material: whether the machine heard *beber* or *vivir*. The
instructor is the person who knows, and making admins the only approvers puts
a fluent reviewer of every offered language in the path of every lesson.

**What keeps it honest.** `APPROVED` requires `reviewed_by` and `approved_at`
in the database, so an approval always names someone; and an edit after
approval returns the transcript to `IN_REVIEW`, so an approval cannot be
carried over content it was not given for.
