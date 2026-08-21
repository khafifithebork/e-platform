# M7 — Learning Experience

**Status:** Approved 2026-08-21. Branch `feat/m7-learning`. T1 done.
Decisions recorded in `docs/adr/016-m7-learning-decisions.md`.

Sources: `architecture.md` §5.1 ERD, §5.2 (denormalised counters), §6.2,
§10 M7. Invariant 3. ADR-014 §3 (the risk that lands here first).

---

## 1. Objective

Watch → progress persists → resume across devices → course completes.

---

## 2. Decisions — settled 2026-08-21

| # | Decision | Outcome |
|---|---|---|
| 2.1 | Does enrolment grant access | **No.** Fixed by invariant 3, not open. |
| 2.2 | Completion rule | **Watched time ≥ 90%, or an explicit mark.** |
| 2.3 | `completed_lesson_count` | **Derived**, declining §5.2's default. |
| 2.4 | Frontend scope | **Backend plus one minimal lesson page.** |

### 2.1 Does enrolment grant access? — **no**, and this is the one that matters

I am stating this rather than asking, because the answer is fixed by invariant
3 and getting it wrong would quietly undo M4.

An `Enrollment` row is a **progress container and a bookmark**. It records
that somebody started a course, where they got to, and when they finished. It
**never** appears in an access decision. `resolve_access` is untouched by this
milestone, and a test will assert that enrolling grants nothing and that
un-enrolling takes nothing away.

The failure this avoids is specific and tempting: "you must be enrolled to
watch" reads like a sensible rule, and it is a second entitlement
implementation. The two would disagree the first time somebody's subscription
lapsed while an enrolment row survived.

**What I do need you to decide is below.**

### 2.2 What counts as completing a lesson? — **settled: watched time, with an explicit override**

§10 M7 asks for this to be defined "precisely *once*" and put in a service,
and names it as your brainstorm's Trap 3.

The ERD offers two different numbers, and the choice between them is the whole
decision:

- `max_position_seconds` — the furthest point reached. **Dragging the scrubber
  to the end sets this to the end.**
- `watched_seconds` — time actually spent watching.

| Option | Completion when | What it gets wrong |
|---|---|---|
| **Watched time + override** (recommended) | `watched_seconds ≥ 90%` of duration, **or** the learner marks it complete | Nothing, unless a client lies — see below |
| Furthest point | `max_position_seconds ≥ 90%` | A learner who scrubs to the end has "completed" a lesson they never heard, and for language learning that is the whole value gone |
| Explicit only | The learner says so | Honest and simple, but a course never completes itself and "resume" has nothing to resume toward |

**Worth being plain about:** any of these is client-reported and therefore
forgeable. The point is not fraud prevention — a learner who wants to mark
their own lesson complete may — it is not marking something complete
*by accident* when somebody drags a scrubber.

**90% is a guess** and will be a named setting, not a literal.

### 2.3 `completed_lesson_count`: stored or derived? — **settled: derived**

`architecture.md` §5.2 lists it as deliberately denormalised, with a nightly
reconciliation job, so **recommending otherwise is declining a document** and I
am flagging it rather than quietly choosing.

The document's reason is real — catalogue cards aggregating across three
tables per card. But this counter is per *enrolment*, not per catalogue card:
it appears on "my courses", which lists the handful of courses one person is
taking. A single annotated query answers that, and §5.2's own sentence is that
denormalised counters "*always* drift eventually".

**Settled: annotate it**, measure it (ADR-009), and denormalise only if a
measurement says so. That inverts the document's default deliberately, and
ADR-016 §3 records why so the mismatch is not read as an oversight.

### 2.4 Does M7 include the frontend player? — **settled: yes, minimally**

§10 M7 lists "player integration, transcript panel", and the deliverable is
phrased as an experience rather than an API: *watch → progress persists →
resume across devices*. That cannot be demonstrated by endpoints alone.

**Settled: the backend in full, plus one lesson page** — a player, a
transcript panel, and progress reporting — in the style M2 T9 established. Not
a designed product surface; enough to prove the loop end to end, so that
"resume across devices" is something somebody has watched work rather than a
claim.

---

## 3. Model sketch

**`Enrollment`** — `user`, `course`, `last_lesson`, `started_at`,
`completed_at`. Unique on `(user, course)` (§5.3 calls this correctness, not
speed). **No access meaning.**

**`LessonProgress`** — `user`, `lesson`, `last_position_seconds`,
`max_position_seconds`, `watched_seconds`, `completed_at`. Unique on
`(user, lesson)` — §5.3 again names this as correctness: it prevents duplicate
rows from concurrent writes, which is exactly what a progress heartbeat
produces.

Constraints in the database (invariant 11): positions non-negative;
`max_position_seconds ≥ last_position_seconds`, since the furthest point
reached cannot be behind the current one.

---

## 4. Abuse cases — these become the first tests

1. **Enrolling grants no access.** A learner with no subscription who enrols
   still cannot watch. The single most important test in this milestone.
2. **Un-enrolling takes no access away** from someone who is entitled.
3. Progress for a lesson the caller is **not entitled to** is refused — a
   learner cannot record having watched what they cannot watch.
4. A learner cannot read or write **another learner's** progress → 404.
5. Progress is **upserted**, not appended: a heartbeat every fifteen seconds
   for an hour is one row, not two hundred and forty.
6. `max_position_seconds` **never moves backwards**, so rewatching from the
   start does not un-complete a lesson.
7. A **completed** lesson stays completed even if progress is later reported
   lower.
8. The **transcript panel serves only APPROVED** transcripts — ADR-014 §3's
   risk, arriving exactly where that ADR predicted.
9. Course completion is decided in **one place**, and a test asserts no second
   definition of "complete" exists outside it.
10. Progress writes are **throttled**, provoked rather than assumed.

---

## 5. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR for §2 | approval |
| T2 | `Enrollment`, `LessonProgress` + constraints | T1 |
| T3 | Progress recording service, upsert + completion rule | T2 |
| T4 | Progress endpoint, entitlement-gated and throttled | T3 |
| T5 | Resume: "my courses", last lesson, next lesson | T3 |
| T6 | Course completion rule and `completed_at` | T3 |
| T7 | Transcript panel endpoint, APPROVED only | T2, M6 |
| T8 | Frontend lesson page: player, panel, heartbeat (§2.4) | T4, T7 |
| T9 | Abuse cases, query counts | all |
| T10 | Schema, types, ADRs, close-out | T9 |

---

## 6. Not in M7

- **No new access rules.** See §2.1.
- **No certificates.** Completion is a date, not a document.
- **No notifications** on completion. M11, with the two visibility gaps
  already outstanding from M5 and M6.
- **No search over transcript text.** M11.
