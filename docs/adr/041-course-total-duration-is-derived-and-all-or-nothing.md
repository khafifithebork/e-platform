# ADR-041 — A course's total duration is derived, and withheld unless complete

**Status:** Accepted by the owner on 2026-10-29.
**Scope:** `PublicCourseDetailSerializer.total_duration_seconds` and the
`published_course_detail` selector.
**Closes:** the duration third of roadmap E8 (`docs/specs/frontend-roadmap.md` §E).

## Context

Roadmap E8 recorded three things a course page cannot state because the backend
does not model them: objectives, prerequisites and total duration. Verified
2026-10-03: `Course` has no such columns and no serializer exposed a duration,
so a page claiming any of them would be inventing it (§6).

**Duration is the one of the three that needs no new column.** The transcoding
task already writes `MediaAsset.duration_seconds` from what the video provider
reports, so the number exists as a fact about the file rather than something a
person typed. The other two are content that does not exist anywhere yet, and
they are not decided here.

## Decision

**1. Derived, never stored.** `_with_total_duration` annotates the sum in SQL.
A `Course.total_duration_seconds` column would be a second answer to a question
the lesson rows already answer, kept in step by a job that can fall behind —
the shape invariant 3 refuses for access and invariant 13 refuses for
transcripts. The ORM path `sections__lessons__media_asset__duration_seconds` is
a string, so `catalog` still imports nothing from `media_assets`.

**2. `None` unless every lesson has been measured.** This is the decision worth
the ADR. A ten-lesson course with nine measured lessons would otherwise publish
nine lessons' minutes as its total — an understatement presented as a fact,
which is what §6 is about. A learner choosing whether to start a course is
better served by no number than a wrong one, and `None` is something the
catalogue can render as silence.

A lesson with no asset at all and a lesson whose asset is still transcoding are
treated identically. The learner cannot tell them apart and neither can be
counted.

**3. A course with no lessons is `None`, not `0`.** "No lessons yet" and "zero
minutes long" are different claims and only one of them is true.

**4. Detail only, not the catalogue card.** The annotation adds a GROUP BY and
two joins, and `published_courses` is what every public list, filter and search
queryset builds on. Putting it there would change the plan of all of them to
serve a number only the detail page shows. A test pins the card's *absence*, so
adding it later is a decision somebody makes rather than a side effect.

**5. The field is always present, and nullable.** Null rather than absent: a key
that disappears when the value is unknown makes the client infer the difference
between "no duration" and "an older API", which is the silent-field failure
`get_instructor_name` already documents in that serializer.

## Consequences

The API gains one nullable integer on the course detail response; the schema and
the frontend types are regenerated from it (invariant 16). No migration, no
model change, no new dependency, no cost.

**The number will be `None` for every course in the repository today**, because
`MediaAsset` rows exist only in fixtures and none carries a provider-reported
duration. That is correct rather than a defect, and it is the same reason
roadmap E7 cannot be answered yet: the subject does not exist until a real
lesson is uploaded. The field starts reporting the moment one is.

Measured, not assumed: the annotation folds into the existing course query, so
the detail page still costs four queries regardless of how many lessons it has.

## What this does not decide

**Objectives and prerequisites — the other two thirds of E8 — are untouched.**
Each needs a shape before it needs a column: whether objectives are one prose
block or an ordered list of short statements, and whether a prerequisite is free
text or a relation to another `Course`. Those choices determine the API, the
admin surface and the course page, and a wrong one costs a migration to undo.
They are the owner's to make, and roadmap E8's framing of "a field" is too thin
to pick from.

**Where the duration is shown is a separate change.** This ADR makes the number
available and correct. Rendering it on the course page — and choosing how to
format it, including in the two interface languages ADR-033 covers — is frontend
work that has not been done.
