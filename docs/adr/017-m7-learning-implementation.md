# ADR-017 — M7 learning: what implementation settled

**Status:** Accepted
**Date:** 2026-08-21
**Companion to:** ADR-016 (decisions taken before code).

---

## 1. A course completes when every lesson does, and never un-completes

**Decision.** `Enrollment.completed_at` is set the moment the last lesson in
the course completes. **All** lessons, not a proportion. The date is then
**never cleared and never recomputed.**

**Why not a proportion.** A second threshold beside
`LESSON_COMPLETION_THRESHOLD` is a second number to guess and a second thing to
disagree about, and it buys nothing that is not already there: a learner who
considers a lesson skippable can mark it complete themselves (ADR-016 §2). One
rule, with an override already built in.

**Why it never recomputes.** An instructor who adds a lesson does not un-finish
everyone who completed the course. This is the same principle that stops
rewatching a lesson unfinishing it, one level up: progress recording must not
be able to take away something a learner earned.

**The visible consequence, chosen rather than overlooked.** A course can report
*three of four lessons complete* beside a completion date. That reads as a bug
until you know it was decided, so `test_and_the_counts_say_what_is_actually_true`
asserts exactly that shape.

**What this gives up.** A learner one lesson short whose remaining lesson is
*deleted* is never re-evaluated, and stays incomplete. Closing it means
recomputing on lesson deletion. There is no lesson-deletion flow in the product
yet — it arrives with M10 moderation — so building for it now would be
speculative.

**Evaluated only on the transition.** The rule runs when a lesson has just
completed, because that is the only event that can change its answer. On every
heartbeat it is two counting queries per beat on the highest-frequency write in
the product, re-answering a question whose inputs had not moved. Both halves
are pinned: no counting queries on an ordinary beat, counting queries when a
lesson completes.

---

## 2. The bookmark is written only when it moves

**Decision.** `_bookmark` reads the enrolment and writes `last_lesson` only if
it changed.

**Why.** The first version used `update_or_create`, which rewrote the same
value on every heartbeat — every fifteen seconds, per learner, per open lesson,
storing what was already there plus a fresh `updated_at`. This is the
highest-frequency authenticated write in the product.

**Why it is here and not in a performance pass.** The query-count assertion
failed at 14 against a predicted 10. Four were savepoints — pytest-django wraps
each test in a transaction, so `transaction.atomic` becomes a savepoint pair
production never pays for. Filtering those and pinning 10 would have been
correct and would have preserved the wasteful write. ADR-009 says to fix an
avoidable cost rather than pin it; the steady state is now nine real queries,
with a positive twin proving the bookmark still advances when the learner
changes lesson.

`updated_at` is set by hand in that `UPDATE`, because `.update()` bypasses
`auto_now` and a timestamp disagreeing with a row that genuinely changed is the
sort of thing somebody later trusts.

---

## 3. Ordering "my courses" is a client concern, and says so

**Decision.** `courses_in_progress` leaves ordering to the paginator, which is
fixed on `("-created_at", "-pk")`. `last_activity` is returned as data.

**Why.** "Continue learning" wants most-recent-activity first, and that is a
`Max()` over the learner's progress rows. A cursor needs a stable, unique,
indexed column to page on, and an aggregate is none of those. Pretending
otherwise gives duplicate and skipped rows under paging.

**What is accepted.** For a learner with fewer than twenty courses — every
learner, realistically — the page is complete and the client can sort it
exactly. Beyond that it degrades. Fixing it properly means a real column and a
measurement first, not a column added on the strength of this paragraph.

---

## 4. `distinct=True` earns its place on one count, not both

**Decision.** Both counts in `courses_in_progress` carry `distinct=True`, and
the docstring says which one needs it.

**Why this is worth an ADR entry.** All nineteen tests passed on the first run,
so the guard was reverted to check the tests could see it — and all nineteen
still passed. With a single learner the lesson-to-progress join is one-to-one
and a non-distinct count is *accidentally* right. A classmate watching the same
course is what makes a four-lesson course report eight.

On `completed_lesson_count` the word is genuinely inert: the `FILTER` narrows to
one learner and `one_progress_row_per_lesson` means that is at most one row per
lesson. It is kept because it costs nothing and the alternative is a count whose
correctness depends on a constraint in another file — but the comment says that,
rather than claiming a protection it does not provide.

**The general form.** This is ADR-006 again: a control nobody has watched fail
is not known to work. It applies to assertions as much as to code.

---

## 5. ADR-014 §3's risk arrived exactly where it said it would

**Decision.** The transcript panel calls `approved_transcript_for` and never
touches `Transcript.objects`, and the test that holds this is a **sweep** that
walks the URL configuration for every lesson-scoped route.

**Why the sweep rather than the panel's own 404.** ADR-014 §3 put the whole
weight of "unreviewed subtitles are worse than none" at the point of serving
rather than at publication, and named the cost: *anything else that renders
segments must apply the same filter*. M6 had one renderer, so the rule was easy
to keep. M7 adds the second, which is when a rule like that usually stops
holding. Removing the `APPROVED` filter fails the sweep with both leaking routes
named by URL.

The sweep needs its own twins, because a walk that returns nothing passes every
assertion inside it: one asserts it finds at least four routes including both
transcript ones, and one asserts that after approval the same words are found at
exactly the VTT and panel routes.

**A separate learner-facing serializer**, not a subset of the reviewer's.
`status`, `confidence`, `error_message` and `kind` describe how the text was
produced, and `status` in particular would let a learner infer that unreviewed
words exist — the thing being kept from them. `is_edited` goes too: it marks the
lines a machine got wrong, which tells a learner about our pipeline rather than
about the language.

---

## 6. Do not report a position before reading the stored one

**Decision.** The player refuses to send any heartbeat until the initial
progress fetch has returned, and a beat of "nothing watched, nowhere reached" is
never sent.

**Why it is a rule and not a bug fix.** Without it the loop writes a playhead of
zero over a real bookmark. The ticker is installed on mount and its cleanup
reports a final beat; React Strict Mode runs that cleanup immediately, before
the fetch saying where the learner was has returned. Watched live: a lesson
resumed at 0:00 having just destroyed the one thing this milestone exists to
prove, with `max_position_seconds` still at 46 in the row as the fingerprint —
the constraint held while the value it guards was overwritten.

**Why no test would have caught it.** There is no frontend test runner, and
adding one is a §5 dependency decision. But the shape is worse than that: the
bug lives in the interaction between an effect's lifecycle and an in-flight
fetch, which is exactly what a unit test of `worthSending` mocks away. ADR-016
§4 asked for a page somebody had watched work. This is what that was for.

---

## 7. Two claims corrected, and what they have in common

**The transcript prefetch.** T7's test said the prefetch is what stops six
hundred cues costing six hundred queries. It is not: a reverse foreign key
collection is one query however many rows it holds, and removing the prefetch
leaves the test passing. The prefetch buys the ordering and one query rather
than two. The count stays pinned — serializing per cue is a real way to fan out
later — but the comment no longer describes a protection that was never there.

**The deferrable constraint (M3, restated here because the pattern repeats).**
A comment claimed a bulk reorder needed deferral. It did not; PostgreSQL checks
deferrable constraints at end of statement and `bulk_update` is one statement.

**What they share.** Both were confident sentences about *why* something works,
written next to code that does work. The code was right and the reason was
wrong, which is the failure mode a passing test cannot see. The only thing that
caught either was removing the mechanism and watching what happened — ADR-009's
"measure, do not reason" applied to explanations, not just to query counts.

---

## 8. `CSRF_TRUSTED_ORIGINS` is required, not optional

**Decision.** Read from `DJANGO_CSRF_TRUSTED_ORIGINS`, empty by default, set in
every environment.

**Why it was missing.** Django compares the browser's `Origin` against its own
host. Next.js forwards its rewrite destination as the `Host` header — the fact
`local.py` already records about `ALLOWED_HOSTS` — so Django's idea of its
origin is `api`, the browser's is `localhost:3000`, and they never match. Every
unsafe request through the proxy was refused, **including login**. Nothing
noticed because the Django test client skips CSRF, and DRF only enforces it
inside `SessionAuthentication`, so an anonymous POST never reaches the check at
all.

**Why empty rather than a permissive default.** A deployment that forgets this
fails loudly on its first write rather than quietly trusting a guessable origin.

**M13 must set it** to the public origin. It is not a credential and belongs in
ordinary deploy configuration.

---

## 9. What M7 did not do

- **No certificates.** Completion is a date.
- **No notifications** on completion — M11, alongside the two visibility gaps
  still outstanding from M5 and M6.
- **No search over transcript text** — M11.
- **No catalogue or course pages.** M7 ships one lesson page, reachable only by
  lesson id, because there is nothing yet to link from. The nicer URL and the
  server-rendered shell belong with the catalogue surface.
- **No frontend test runner.** Adding one is a §5 decision. Until then the
  frontend's verification is `tsc`, `eslint`, `next build`, and running it.
