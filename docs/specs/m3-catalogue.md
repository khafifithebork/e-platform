# Spec: M3 — Catalogue & Course Domain

**Status:** Draft, awaiting approval. No code written.
**Milestone:** M3 (`docs/architecture.md` §10)
**Prerequisites:** M0, M1, M2 complete.

---

## Assumptions I'm making

1. **Curation is the product, not a workflow detail.** An instructor can never
   publish their own course. `architecture.md` §3 opens with "curated
   (admin-approved)", so approval is a hard rule enforced in a service, not a
   convention.
2. **Lessons carry no media yet.** `MediaAsset` is M5, so a lesson in M3 is
   title, body, type, position and preview flag.
3. **No entitlement gating.** `resolve_access` does not exist until M4, so
   lesson *content* is not gated yet. Public endpoints expose published
   metadata only, and the gate lands in M4.
4. **No search, no filters beyond the obvious.** Postgres full-text search and
   `search_vector` are M11 (§10). M3 ships list and detail.
5. **One instructor per course** (§5.1 — `COURSE.instructor_id`). Co-teaching
   is not modelled.

---

## Objective

Let an instructor build a course, submit it for review, and let an admin
approve it — after which, and only after which, the public can see it.

The whole product rests on the last clause. Everything M4 gates, M5 uploads to
and M7 tracks progress against is a `Lesson` that got here.

---

## Threat model

### Trust boundaries

| Boundary | Untrusted input |
|---|---|
| Instructor CRUD | A course, section or lesson id belonging to somebody else |
| State transitions | A request to move a course to `PUBLISHED` |
| Public catalogue | A slug for something not published |
| Reordering | A list of ids, possibly from another course |

### Assets

Unpublished course content, the integrity of the published catalogue, and —
most valuable — **the approval gate itself**. An instructor who can publish
their own work has removed the product's central promise.

### STRIDE, applied

| Threat | Concrete here | Control |
|---|---|---|
| **Spoofing** | Acting on a course you do not own | `get_queryset()` scoped to `request.user`, always |
| **Tampering** | `PATCH` a published course back into an editable state, or edit somebody else's | Transitions only via a service; scoped querysets |
| **Repudiation** | "I never approved that course" | `CourseReviewEvent` records reviewer, decision and notes |
| **Information disclosure** | Probing slugs to find unpublished courses | Public querysets filter to `PUBLISHED`; unscoped objects answer **404**, never 403 (§6.3 — a 403 confirms existence) |
| **Denial of service** | A catalogue page that fans out per card | Query counts asserted on list endpoints |
| **Elevation of privilege** | Instructor publishes their own course | Only an admin may reach `PUBLISHED`; the instructor's only forward move is `submit-for-review` |

### Abuse cases — these become the first tests

1. Instructor A requests instructor B's course → **404**, not 403.
2. Instructor A `PATCH`es B's course → 404, and B's course is unchanged.
3. An instructor calls whatever endpoint publishes → refused, whatever they send.
4. An instructor sets `status: "PUBLISHED"` in a `PATCH` body → ignored.
5. The public catalogue never returns a `DRAFT`, `IN_REVIEW` or `ARCHIVED` course.
6. A public detail request for an unpublished slug → 404.
7. Reordering with ids from another course → refused, and nothing moves.
8. A lesson slug is unique within its course, so `/courses/x/lessons/y/`
   resolves to exactly one lesson.
9. The catalogue list does not fan out — query count is asserted and pinned.

**ADR-006 applies to every one of these.** M2 shipped two controls that were
configured correctly and did nothing. A scope filter that silently matches
everything, or a transition guard nobody calls, would fail identically — so
each control gets a test that provokes it and watches it refuse.

---

## Success criteria

- An instructor can create a course, add sections and lessons, reorder them,
  and submit for review.
- An admin can approve or reject; only approval publishes.
- The public sees published courses and nothing else.
- **Every abuse case above has a test that fails without its control.**
- Coverage: permissions and scoping **~95%** (§8.1); services ~85%.
- No N+1 on any list endpoint; query counts asserted.
- Migrations reviewed for lock behaviour; `check --deploy`, ruff, tsc clean;
  schema and types regenerated.

---

## Scope

### In

| Area | Detail |
|---|---|
| Models | `Language`, `Course`, `Section`, `Lesson`, `CourseReviewEvent` |
| State machine | `DRAFT → IN_REVIEW → PUBLISHED → ARCHIVED`, transitions in a service |
| Ordering | `position` per parent, deferrable unique, bulk reorder in one transaction |
| Instructor API | Course/section/lesson CRUD, scoped; `submit-for-review` |
| Admin | Review queue and approve/reject via **Django Admin** (§6.2 — "deliberately thin") |
| Public API | `languages/`, `courses/`, `courses/{slug}/`, lesson detail |

### Out, deliberately

- **Entitlement gating** — M4. Lesson *content* is not protected yet, and the
  spec must not pretend otherwise.
- **Media** — M5. No upload, no `MediaAsset`, no duration.
- **Search, filters, related courses** — M11.
- **`search_vector`** — M11, and adding the column early means a GIN index to
  maintain with nothing reading it.
- **Denormalised counters** (`lesson_count`, `total_duration_seconds`) — see
  open question 3.
- **`is_trial_featured`** — M9. Nothing reads it before then.
- **A custom admin API** — §6.2 puts the review queue in Django Admin for
  approximately zero effort; a bespoke UI is M10.

---

## Open questions

### 1. Where is a lesson slug unique? *(blocks the Lesson model)*

`architecture.md` §5.3 indexes `course.slug` uniquely but says nothing about
lesson slugs, while §6.2 routes `/courses/{slug}/lessons/{lesson_slug}/`. That
URL only resolves if the lesson slug is unique **per course** — but `Lesson`
belongs to a `Section`, not directly to a `Course`.

- **A. Unique per course**, enforced by a constraint that reaches through the
  section. Requires either a denormalised `course_id` on `Lesson` or a
  validation in the service.
- **B. Unique per section**, and the URL becomes ambiguous — two sections could
  both hold `introduction`.

**Recommendation: A, with a `course` foreign key on `Lesson` alongside
`section`.** It makes the constraint a plain database `UniqueConstraint`
(invariant 11) rather than a service-layer check that a bulk import bypasses,
and it makes the lesson→course query one hop instead of two on the hottest
read path. The redundancy is real and worth it; a check constraint can keep
`lesson.course_id` consistent with `lesson.section.course_id`.

### 2. Can an admin publish directly, or only approve a submission?

- **A. Only via review.** `DRAFT → IN_REVIEW → PUBLISHED`. One path, easy to
  audit.
- **B. Admins may also publish a draft directly**, skipping review.

**Recommendation: A.** Every publish then has a `CourseReviewEvent` behind it,
which is what makes "why is this live?" answerable. An admin who wants to
publish their own course can submit it and approve it — two clicks, and a
record.

### 3. Denormalised counters now or later?

§5.2 wants `lesson_count` and `total_duration_seconds` on `Course` to keep
catalogue cards off a three-table aggregate, and warns they always drift.

**Recommendation: later.** `total_duration_seconds` cannot be computed until
M5 provides durations, and a counter maintained before anything reads it is a
correctness liability with no benefit. Revisit when the catalogue page exists.

### 4. Does M3 ship the public catalogue, or only the builder?

§10 lists both under M3 deliverables, which is a large milestone.

**Recommendation: both, but the catalogue read-only and unfiltered.** The
public endpoints are what prove the scoping works — abuse cases 5 and 6 have
nowhere to live otherwise.

---

## Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | `Language`, `Course` models + migration | — |
| T2 | The publish state machine as a service, with transitions and guards | T1 |
| T3 | `Section`, `Lesson`, ordering constraints | T1 |
| T4 | Instructor course CRUD, scoped — **IDOR tests first** | T2 |
| T5 | Section/lesson CRUD + bulk reorder in one transaction | T3, T4 |
| T6 | `submit-for-review`; `CourseReviewEvent` | T2 |
| T7 | Django Admin: review queue, approve/reject | T6 |
| T8 | Public catalogue: languages, course list, course detail | T2 |
| T9 | Query-count assertions on list endpoints | T8 |
| T10 | Schema + types; ADR for anything settled |

---

## What I would deliberately not build

- A generic state-machine library. Four states and three transitions is a
  service function with a lookup table, not a dependency.
- Soft deletes. Nothing asks for them, and `ARCHIVED` covers the real need.
- A permissions framework. Role plus `get_queryset()` scoping is the whole
  requirement (§4.4).
- Anything touching billing. Open decision #1 is still unresolved.
