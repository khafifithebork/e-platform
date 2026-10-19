# ADR-039 — Instructor content editing excludes destructive deletion

**Status:** Accepted by the owner on 2026-10-19.
**Scope:** Instructor course, section and lesson APIs.

## Context

The M3 specification describes scoped instructor CRUD. Its implementation used
DRF's `ModelViewSet`, which also supplied destructive DELETE actions. ADR-017
§1 later deferred completion recalculation on lesson removal on the assumption
that no product lesson-deletion flow existed. The inherited API actions made
that assumption false.

Regression tests reproduced successful deletion of an owned course in every
publication state and successful deletion of sections and lessons. A course
with an enrolment instead raised `ProtectedError`. Section/lesson deletion
can cascade to `LessonProgress` and clear an enrolment's lesson bookmark.
Neither outcome is an intentional instructor retention policy.

## Decision

Remove the destroy action from all three instructor viewsets, including draft
content. Compose their shared editing base from create, retrieve, update and
list mixins without `DestroyModelMixin`. Leave the course-scoping mixin and
read-only review-event viewset separate.

For an authenticated, permitted instructor, DELETE on these detail routes
returns **405 Method Not Allowed**, whether the identifier belongs to the
instructor, another instructor, or no object. There is no object lookup for
an unsupported action, so the response does not reveal existence. Existing
authentication checks still apply. Supported reads and edits retain
their scoped 404 behavior. OPTIONS and the generated OpenAPI/types no longer
advertise DELETE.

The existing administrator archive service remains the way to withdraw a
published course. This decision supersedes only the DELETE portion of M3's
instructor CRUD scope; creation, edits, submission, reordering and review
remain unchanged.

## Alternatives

- **Block DELETE using `http_method_names`:** workable, but retains an inherited
  destroy action. Omitting that action makes the intended API surface explicit.
- **Keep deletion and add guards/cleanup:** requires decisions about progress,
  completion, media retention and permitted publication states. Those decisions
  are not prerequisites for safe instructor editing and are deferred.

## Consequences and verification

Clients relying on instructor DELETE must stop using it; the three generated
delete operations are removed. There is no instructor frontend deletion flow
to replace. No model, migration, dependency, billing or entitlement rule changes.

Tests cover all four course states, identical foreign/missing responses, absent
DELETE in Allow/OPTIONS, and preservation of curriculum, enrolment bookmarks
and progress after each rejected deletion. Existing API tests continue to
cover the supported actions, and the schema snapshot guard checks regeneration.

This is an API restriction, not a global database retention mechanism. Django
Admin, direct ORM operations, media lifecycle behavior and any future erasure
workflow are outside this batch. Reintroducing instructor deletion requires
an approved retention design and tests for its effects on learner history.
