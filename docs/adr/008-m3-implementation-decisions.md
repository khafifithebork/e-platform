# ADR-008 — M3 catalogue: decisions taken during implementation

**Status:** Accepted
**Date:** 2026-08-18
**Supersedes:** nothing. **Amends:** ADR-007 §3 (see §4 below).
**Context:** M3 — Catalogue domain. Companion to ADR-007, which recorded the
decisions taken at spec time; this records the ones that only appeared once
code existed.

---

## 1. Sections and lessons nest under their course, using the stock router

**Decision.** `/api/v1/instructor/courses/{id}/sections/` and `.../lessons/`,
registered with a regex prefix on DRF's `DefaultRouter`. No
`drf-nested-routers`.

**Why nested rather than flat.** With the course in the path, every nested
route resolves ownership through the same scoped queryset the course routes
use. A flat `/sections/{id}/` would need its own scope filter, and the day
someone adds a fifth such endpoint is the day one of them is written without
it. Nesting removes the opportunity rather than documenting it.

**Why not the library.** `drf-nested-routers` reads better than
`courses/(?P<course_pk>[^/.]+)/sections`. It is also a new dependency, which
CLAUDE.md §5 gates on approval, and two registrations do not justify the ask.
Revisit if a third level of nesting appears.

**Consequence.** All course-scoped viewsets share `_CourseScopedMixin`, which
is a **mixin and not a viewset base class**. That distinction is load-bearing —
see ADR-009 §3.

---

## 2. Reorder is all-or-nothing and must name every row

**Decision.** `POST .../sections/reorder/` takes `{"order": [id, ...]}` and
refuses with 400 unless the list is exactly the set of ids belonging to that
parent — no foreign ids, no omissions, no duplicates. Nothing is written until
the whole payload validates.

**Why all-or-nothing.** A reorder payload is a list of ids, which makes it the
easiest place in the API to smuggle in a row belonging to somebody else. The
tempting implementation validates each id as it applies it, which leaves the
caller's own rows half-moved when the foreign one is rejected: their course
ends up in an order they never asked for. Abuse case 7 asserts that *nothing*
moves, not merely that the foreign row is untouched.

**Why omission is also refused.** A row not named keeps a position another row
is about to take. Accepting partial orders would mean either a silent
collision or a silent renumber, and neither is something the caller can
predict.

**Consequence.** Clients must send the full order for a section list. For the
sizes involved — sections and lessons within one course — that is a handful of
ids, and the alternative is an API whose result depends on rows the caller did
not mention.

---

## 3. `CourseReviewEvent` records submissions, not only decisions

**Decision.** Submitting a course for review writes an event. The fields are
`actor`/`action`, not `reviewer`/`decision`.

**Why not a `Course.submitted_at` column.** The review queue orders on
submission time. A column is mutable state saying what is true now — any later
edit corrupts it, so an instructor fixing a typo would jump the queue — and it
cannot hold the reject → fix → resubmit loop, which is a real support
question. This is the same argument the model already makes for not trusting
`status` to explain why a course is live.

**Why the rename.** Once submissions are on the trail, the actor is the
instructor on one row type and an admin on every other, so `reviewer` would
have been false half the time. Migration `0004` is hand-written: the
autodetector recognised one rename and proposed dropping the other column and
adding a new one, which is indistinguishable from a rename on an empty table
and destroys history on a populated one.

**Boundary.** Nothing derives publication from this table. The state machine in
`services.py` decides; the trail explains. A forged event would mislead a
human, not grant access — tested explicitly.

---

## 4. `notes` are visible to the instructor — amends ADR-007 §3

**Decision.** `CourseReviewEvent.notes` is exposed to the course's instructor
at `/instructor/courses/{id}/review-events/`, read-only.

**Why.** A rejection the instructor cannot read tells them nothing to fix,
which makes the field pointless. ADR-007 §3 recorded the review trail without
saying who could see it; this settles it.

**Known gap, deliberately not closed.** There is one `notes` field and it is
instructor-visible. An admin wanting a private scratchpad does not have one,
and nothing enforces the convention beyond a comment on the model and the
label in the admin form. Adding `internal_notes` is speculative until someone
asks for it — but if an admin ever writes something they would not say to the
instructor, this is where it leaks.

---

## 5. Django Admin is built and left unrouted

**Decision.** `apps/catalog/admin.py` registers the review queue and its
actions. `config/urls.py` still does not route `admin/`. The suite reaches the
admin through `tests/urls_with_admin.py`.

**Why both.** M3's task list asks for the admin review queue; `config/urls.py`
records a decision that admin stays unreachable until M10 hardens it — obscure
path, staff-only, 2FA, audit logging. Those disagree, and CLAUDE.md §9 requires
reporting rather than silently choosing. They reconcile: the `ModelAdmin`
classes are the deliverable, the URL exposure is M10's, and building the first
without the second costs nothing.

**Why the test urlconf lives in `tests/`.** A module in `config/` that routes
admin is one settings typo away from being the production urlconf.

**What M10 still owns.** Who gets `is_staff` at all. A staff account that is
not `role == ADMIN` cannot publish — the service refuses, and that is tested
against a superuser to make the point — but it *can* edit course fields.

---

## 6. The public catalogue omits lesson bodies rather than gating them

**Decision.** `PublicLessonSerializer` has no `body` field. Not hidden by a
condition, not empty-stringed — absent from `fields`.

**Why.** Entitlements arrive in M4, so in M3 there is nothing to gate with. A
serializer that *could* render paid content and relies on a branch to decide
is one wrong branch from serving it; a serializer with no such field cannot.
Curriculum structure is still exposed, because the shape of a course is the
sales pitch and hiding it would be as wrong as leaking the content.

**Consequence for M4.** When `resolve_access` exists, preview and entitled
playback are a *different serializer* selected by the resolver's decision —
not a conditional field added to this one. Adding the field back here is the
regression to watch for.

---

## 7. `catalogue` throttle scope at 120/min

**Decision.** Public catalogue endpoints use a `catalogue` throttle scope,
default 120/min, rather than the 60/min anonymous baseline.

**Why.** Browsing a catalogue is several requests per page, so the general
anonymous limit would throttle ordinary use.

**Status of the number: guessed.** CLAUDE.md §6 forbids inventing rate limits
and this is the closest thing to one in the milestone, so it is flagged rather
than buried. It is our own limit, not a provider fact, but it has not been
measured against real traffic. Revisit when there is traffic to measure.

---

## 8. What M3 deliberately did not do

- No enrolment, no progress, no access checks. Entitlements are M4 and the
  catalogue must not grow a private version of them.
- No counters (`lesson_count`, `duration`). ADR-007 §4 defers these; nothing in
  M3 changed that.
- No media. `Lesson.body` is text; video and audio are M5.
- No billing, of any kind. The payment provider decision is still open and the
  standing rule holds.
