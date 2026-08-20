# M6 — Transcription & Subtitles

**Status:** Approved 2026-08-20. Branch `feat/m6-transcription`. T1 done.
Decisions recorded in `docs/adr/014-m6-transcription-decisions.md`.

Sources: `architecture.md` §3.1 (the diagram), §3.5 (the pipeline), §5.2
(transcripts as rows), §5.1 ERD, §6.2, §10 M6. Invariant 13. ADR-012 §1 for
the provider pattern.

---

## 1. Objective

Upload → machine transcript → edit → approve → subtitles in the player.

**Invariant 13 is the shape:** transcripts are structured rows. VTT is a
rendered, cached projection and **never** the stored form. §5.2 gives the
reasons: the review UI becomes CRUD instead of file parsing, "click a line,
seek the video" becomes a `start_ms` lookup, a translation is a second
`Transcript` row against the same asset, and full-text search over lesson
content stays possible.

---

## 2. Decisions — all four settled, 2026-08-20

| # | Decision | Outcome |
|---|---|---|
| 2.1 | Deepgram spend | **None.** Interface plus a fake. |
| 2.2 | VTT cache | **Redis + ETag**, declining the §3.1 diagram. |
| 2.3 | Publish gate | **No gate.** Unapproved transcripts are never *served* instead. |
| 2.4 | Approver | **Instructor, and admins.** |

### 2.1 Does M6 spend anything? — **settled: no**

Deepgram is a paid service and CLAUDE.md §5 gates that. Unlike storage in M5,
there is no free local equivalent, so this is the M4/M5 pattern exactly:
**the documented interface plus a fake**, with the real adapter as a separate
task gated on your approval of the bill.

The fake returns realistic segments — plausible timings, a confidence score,
word-level boundaries — because a fake returning one segment would let the
whole review and rendering path pass while proving nothing about multi-segment
VTT.

**Residual risk, stated as in ADR-012:** the Deepgram integration is unproven
at the end of M6. What is proven is everything around it.

### 2.2 Where is rendered VTT cached? — **settled: Redis, not R2**

**This declines what the §3.1 diagram shows**, which lists R2 as holding
"masters · resources · VTT", so I am flagging it rather than quietly choosing.

A VTT file for an hour of speech is tens of kilobytes and renders from rows
with one query and a string build. Redis is already in the stack, is declared
disposable (§3.4), and a projection is exactly the kind of thing that may be
lost. Putting it in R2 adds an upload on every edit, a second place the
subtitle can be stale, and a cache-invalidation problem for a file that
regenerates in milliseconds.

Served with an **ETag** so the browser revalidates cheaply and an edit
invalidates by content rather than by remembering to purge.

Revisit when subtitles are served at CDN volume — that is the case R2 wins.

### 2.3 Does an unapproved transcript block publication? — **settled: no gate**

**Publication is never blocked.** M3's `approve()` is untouched, and its tests
stay valid.

**What carries the requirement instead.** §10 M6 asks for a publish gate
because *"unreviewed subtitles are worse than none for language learning"* — a
machine transcript teaches learners the wrong words with confidence. That risk
is about **what a learner sees**, not about when a course goes live, so it is
answered where it actually arises: **the VTT endpoint serves only `APPROVED`
transcripts.** A `MACHINE` or `IN_REVIEW` transcript is a 404 to a learner.

This is stricter than a publish gate in the way that matters and looser in the
way that does not. A gate would let an approved-but-wrong transcript through
on day one and block a perfectly good course whose subtitles are still being
typed; refusing to serve unapproved text prevents the actual harm in every
case, including for lessons added to a course that is already live.

**Known consequence, accepted:** a published lesson may have no subtitles for a
while, and nothing tells the learner why. That is a UX gap, not a correctness
one, and it belongs with notifications in M11.

**This amends `architecture.md` §10 M6**, which names a publish gate as a
deliverable. Recorded in ADR-014 §3 rather than silently skipped.

### 2.4 Who approves a transcript? — **settled: the instructor, and admins**

ADR-007 §2 settled that only admins *publish a course*. Approving a
transcript is a different act: it is a language judgement about one's own
content, and the instructor is the person who knows whether the machine heard
"beber" or "vivir". Making admins the only approvers puts a language reviewer
in the publication path for every lesson.

Admins keep the ability, for support.

---

## 3. Model sketch

**`Transcript`** — `media_asset` (FK), `language` (FK), `kind`
(`TARGET`/`TRANSLATION`), `status` (`PENDING`/`MACHINE`/`IN_REVIEW`/
`APPROVED`/`FAILED`), `provider`, `confidence`, `reviewed_by`, `approved_at`.

**`TranscriptSegment`** — `transcript` (FK), `position`, `start_ms`,
`end_ms`, `text`, `is_edited`.

Constraints in the database (invariant 11): `end_ms > start_ms`; position
unique per transcript, **deferrable** so a reorder or a split can pass through
a duplicate (ADR-009 §5 — and it needs the paired IMMEDIATE test, or the
deferral is untested); `APPROVED` requires `reviewed_by` and `approved_at`,
because an approval nobody signed is the audit gap M3's review trail exists to
close.

**`kind` is modelled, only `TARGET` is produced.** A translation needs a
translation provider, which is a second bill and not in this milestone.

---

## 4. Abuse cases — these become the first tests

1. An instructor edits a segment on **someone else's** lesson → 404.
2. An instructor approves a transcript on someone else's lesson → 404.
3. A student cannot read a transcript for a lesson they are **not entitled**
   to — the resolver decides, exactly as playback does.
3b. A learner is served **no transcript at all** unless it is `APPROVED` —
   the control that replaces the publish gate (§2.3), and the one that keeps
   unreviewed subtitles away from learners.
4. A **preview** lesson's transcript is readable anonymously, like its video.
5. Editing a segment marks it `is_edited` — so review is auditable and a later
   re-run cannot silently discard human corrections.
6. Approving requires review: a transcript goes `MACHINE → IN_REVIEW →
   APPROVED`, never straight from `MACHINE`.
7. An approved transcript that is edited **returns to `IN_REVIEW`** — an edit
   after approval is unreviewed content wearing an approval.
8. The rendered VTT is **invalidated by an edit**, asserted by fetching before
   and after rather than by checking a cache key.
9. VTT rendering **escapes** segment text — a transcript is user-supplied
   content rendered into a file a browser parses.
10. A webhook for an unknown transcript creates nothing (invariant 8, as M5).
11. No response exposes the provider's own job id to a learner.

---

## 5. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR for §2 | approval |
| T2 | `Transcript`, `TranscriptSegment` + constraints | T1 |
| T3 | Transcription provider interface + fake | T1 |
| T4 | Task: request transcription when media becomes READY | T2, T3 |
| T5 | Webhook/callback receiver → segments | T2, T3 |
| T6 | Segment editing, scoped | T2 |
| T7 | Review workflow: `IN_REVIEW` → `APPROVED`, re-review on edit | T6 |
| T8 | VTT rendering, cached, entitlement-gated | T2 |
| T9 | Serve only APPROVED transcripts; never gate publication (§2.3) | T7, T8 |
| T10 | Abuse cases, query counts, schema, types, ADRs | all |

---

## 6. Not in M6

- **Translations.** `kind` is modelled; producing them needs another provider.
- **Full-text search** over transcript text. M11.
- **The real Deepgram adapter**, pending §2.1.
- **Word-level karaoke timing.** Segment-level only; the fake returns word
  boundaries so the column can arrive later without a provider change.
