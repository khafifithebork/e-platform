# ADR-016 — M7 learning experience: enrolment is not entitlement

**Status:** Accepted
**Date:** 2026-08-21
**Amends:** `architecture.md` §5.2 (see §3).
**Context:** M7 — Learning Experience. Taken before any code.

---

## 1. Enrolment grants nothing

**Decision.** An `Enrollment` row is a progress container and a bookmark. It
records that somebody started a course, where they reached, and when they
finished. **It never appears in an access decision.** `resolve_access` is not
touched by this milestone.

**Why this was decided rather than asked.** Invariant 3 already settles it:
one resolver, never duplicated, never inlined. But the wrong answer is
unusually tempting here, because *"you must be enrolled to watch"* reads like
an ordinary product rule rather than a second entitlement implementation.

**How it would fail.** The two rules disagree the first time somebody's
subscription lapses while their enrolment row survives — and it survives by
design, because it holds their progress. At that moment a learner either keeps
access they are not paying for, or loses progress they have earned, depending
on which rule the endpoint in front of them happens to consult.

**How it is held.** Tests assert that enrolling grants nothing to someone
without a subscription, and that removing an enrolment takes nothing away from
someone entitled. M4's structural guard already fails the build if any module
outside `entitlements/` compares a subscription status, so a second rule
cannot be written there either.

---

## 2. Completion is watched time, or an explicit mark

**Decision.** A lesson is complete when `watched_seconds` reaches 90% of its
duration, **or** when the learner marks it complete. One service function,
one definition, as §10 M7 requires.

**Why watched time and not the furthest position.** The ERD offers both, and
the difference is a product decision rather than a technical one:
`max_position_seconds` is set by *dragging the scrubber to the end*. A learner
who does that has completed nothing, and for language learning the listening
is the entire value. Marking it complete would be recording an achievement
that did not happen, in the one place a learner looks to know what they have
covered.

**Why an explicit override as well.** Somebody who already speaks the material
should not have to sit through it to clear it from their list, and a course
that can never be finished by a competent learner is its own kind of wrong.

**Stated plainly: this is client-reported and therefore forgeable.** A learner
can tell us they watched. That is fine — the goal is not fraud prevention,
because there is nothing to defraud; it is not marking something complete *by
accident* when somebody drags a scrubber.

**90% is a guess**, and it lives in a named setting rather than a literal, so
the boundary is a value a test moves and changing it is configuration.

---

## 3. `completed_lesson_count` is derived, not stored — amends §5.2

**Decision.** Count completed lessons with an annotation. No stored counter, no
reconciliation job.

**What this declines.** `architecture.md` §5.2 lists `completed_lesson_count`
among the deliberately denormalised counters, to be maintained in the service
layer inside the same transaction, with a nightly reconciliation task.

**Why the document's reasoning does not reach this field.** §5.2's argument is
about catalogue pages: cards that would otherwise aggregate across three
tables *per card*, for every visitor. This counter is per **enrolment**. It
appears on "my courses" — the handful of courses one person is taking — where
a single annotated query answers the whole page.

**And §5.2 makes the counter-argument itself:** denormalised counters "*always*
drift eventually". Accepting drift plus a reconciliation job is a fair trade
for the catalogue's hottest query; it is a poor one for a list of six rows.

**How this is kept honest.** ADR-009: the annotation's cost is measured and
pinned at two dataset sizes. If a measurement says the annotation is the
problem, denormalising is the fix — with the drift and the reconciliation job
accepted knowingly, rather than inherited.

**`lesson_count` and `total_duration_seconds` are untouched by this.** They are
catalogue-card fields and §5.2's reasoning applies to them unchanged; ADR-007
§4 already defers them.

---

## 4. M7 ships one lesson page

**Decision.** The backend in full, plus a single lesson page — player,
transcript panel, progress heartbeat — in the minimal style M2 T9 established.

**Why any frontend at all.** The deliverable is phrased as an experience:
*watch → progress persists → resume across devices*. Endpoints cannot
demonstrate that. "Resume across devices" in particular is the kind of claim
that passes every unit test and fails the first time a person opens a second
browser.

**Why minimal.** A designed lesson experience would be built against no real
lessons and redone once there are some.

---

## 5. What this milestone must not become

ADR-014 §3 predicted that the next reader of transcript segments would be an
interactive transcript, and M7 is where it arrives. **The transcript panel
must serve only `APPROVED` transcripts**, through the same
`approved_transcript_for` selector rather than a second query.

The structural guard from M6 stops that query being written *outside* the
transcripts app. It does not stop a second unfiltered one being written
inside it, which is the specific thing to watch when T7 is reviewed.
