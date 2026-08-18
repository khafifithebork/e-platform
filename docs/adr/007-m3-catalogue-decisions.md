# ADR-007 — M3 catalogue decisions

**Status:** Accepted
**Date:** 2026-08-18
**Related:** `docs/architecture.md` §5.1, §5.3, §6.2, §10 · `docs/specs/m3-catalogue.md`

---

## 1. Lessons carry a `course` foreign key as well as a `section`

`architecture.md` §6.2 routes `/courses/{slug}/lessons/{lesson_slug}/`. That URL
resolves to one lesson only if the slug is unique **per course** — but §5.1 hangs
`Lesson` off `Section`, and §5.3 indexes neither slug. The documents do not
answer the question the URL scheme asks.

**Decision: `Lesson` has both `section` and `course`**, with a
`UniqueConstraint(course, slug)`.

The redundancy is deliberate. Uniqueness enforced in a service is uniqueness a
bulk import, a data migration or a management command walks straight past;
invariant 11 wants the guarantee in the database, and a constraint spanning two
joins is not something Django can express. It also makes lesson-to-course one
hop instead of two on the hottest read path in the product.

A `CheckConstraint` cannot verify `lesson.course_id == lesson.section.course_id`
either — that is a cross-row assertion. The consistency is held by the service
that creates lessons, and a test asserts a lesson cannot be created into a
section belonging to a different course.

## 2. Only an admin publishes, and only through review

**Decision: the sole path to `PUBLISHED` is `IN_REVIEW → PUBLISHED`, performed
by an admin.** There is no direct-publish transition, for admins or anyone else.

`architecture.md` §3 describes the product as curated and admin-approved. If an
instructor can publish, that sentence is false and the catalogue's value —
someone checked this — goes with it.

Routing every publish through review means every published course has a
`CourseReviewEvent` behind it naming who approved it and when. "Why is this
live?" becomes answerable, which §7.2's audit requirement and every future
support ticket depend on. An admin publishing their own course submits it and
approves it: two steps, and a record.

## 3. Denormalised counters wait

§5.2 wants `lesson_count` and `total_duration_seconds` on `Course`.

**Decision: neither in M3.** `total_duration_seconds` cannot be computed until
M5 supplies durations, and §5.2 says itself that such counters always drift. A
counter that drifts before anything reads it is pure liability. Revisit when the
catalogue page that needs them exists.

`search_vector` waits on the same reasoning: a GIN index to maintain with no
query behind it until M11.

## 4. M3 ships the public catalogue as well as the builder

**Decision: both**, with the catalogue read-only and unfiltered — search and
faceting are M11.

Not for completeness. The public endpoints are where "a draft never escapes"
becomes testable; without them, abuse cases 5 and 6 have nowhere to live, and
the scoping would be asserted only against the instructor API that is already
scoped by ownership.

## 5. Consequences

`Lesson` carries a foreign key that a normalised reading would call redundant.
Anyone tempted to remove it should read point 1 first.

The state machine has no escape hatch. Seeding a published course for a demo or
a test fixture means going through the service, which is the intended cost.
