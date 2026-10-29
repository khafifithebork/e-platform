# ADR-040 — Media and transcript authorization lives in services and selectors, not views

**Status:** Accepted by the owner on 2026-10-29.
**Scope:** `media_assets` asset reads and the retry path; `transcripts` review reads.
**Supersedes:** the rationale in the `apps/transcripts/views.py` module docstring, and
the comments in `MediaAssetDetailView`/`MediaAssetRetryView`, which argued the opposite.

## Context

Both apps authorized object-addressed routes by fetching the row from an
unscoped manager and then asking an ownership predicate in the view:

```python
asset = get_object_or_404(MediaAsset.objects.select_related("lesson__course"), pk=pk)
if not may_manage(lesson=asset.lesson, user=request.user):
    return Response(status=404)
```

The pattern was deliberate and documented. `apps/transcripts/views.py` argued
it this way: *"Ownership is checked in the view rather than by a queryset
filter because a transcript and a segment are each addressed by their own id —
architecture.md §4.4 calls exactly that the commonest IDOR in DRF codebases."*

**The premise is right and the conclusion does not follow.** §4.4 names the
unscoped fetch as the IDOR; the remedy CLAUDE.md invariant 10 gives is the
scope filter, not a second step the caller must remember. An id in the path
rather than a parent in the path makes the filter longer to write
(`media_asset__lesson__course__instructor`), not unavailable. And once the
check sits in a view it is also a business-state `if` in a view, which
invariant 2 calls a bug outright.

`retry_processing` was the case where this cost something measurable. Its only
ownership check was in `MediaAssetRetryView`, and the service has a second
caller: the `retry_failed` admin action, which passes through no view. Because
`is_staff` is independent of `Role` (`accounts/models.py`), a staff account
holding nothing but `change_mediaasset` requeued another instructor's asset
through the admin changelist. **This was reproduced against the running code
before the change, not inferred** — the probe signed in as a staff user with
role `STUDENT` and the asset moved from `FAILED` to `UPLOADED`.

The cost of the *write* is provider minutes and a pipeline run on content the
caller has no claim on.

**The first draft of this ADR added "it is not a data-disclosure hole", and a
review of the fix falsified that.** Closing the write left the **read** open:
`MediaAssetAdmin` had no `get_queryset`, so the same account loaded the
changelist and every change form on it, with `source_object_key`,
`provider_asset_id` and `error_message` present. Reproduced, like the write.
The sentence was wrong because it reasoned about one surface — the action's
return value — and called it the whole surface. The API was correctly guarded
throughout; the admin was not.

## Decision

**1. Object reads are scoped in the queryset.** Three selectors return what
the caller may touch: `media_assets.selectors.assets_manageable_by(user)`,
`transcripts.selectors.transcripts_reviewable_by(user)` and
`transcripts.selectors.segments_editable_by(user)`. `transcript_for_review`
requires `user` — a required argument rather than an optional one, because an
optional scope is the one the next caller forgets. Views call
`get_object_or_404` against the scoped queryset and branch on absence only.

**Every object read on these routes, with no exceptions left standing**: the
asset status read, the upload-completion fetch, the retry fetch, the review
screen, the response rendered after a review transition, and the segment edit.
`MediaAssetAdmin.get_queryset` uses the same selector, so the admin cannot
drift from the API.

**2. Services decide for every caller, not only the HTTP one.**
`retry_processing` requires `by` and raises `NotYours`, like `request_upload`
and `complete_upload` already did. The admin action passes `request.user` and
reports refusals rather than appearing to succeed.

**3. Ownership is checked before state.** A caller who gets 409 for a
TRANSCODING asset and 404 for a FAILED one has been told which it is. §6.3
forbids confirming even that, so the ownership branch runs first.

**4. The duplication is pinned rather than trusted.** A rule expressed as both
a queryset and a predicate can drift — which is the argument `may_review`'s own
docstring makes against restating ownership. The predicates stay, because a
service holding an object should not run a query to re-ask; and two test
classes assert the queryset and the predicate answer identically for owner,
other instructor, student, admin, superuser and anonymous.

## Consequences

**One behaviour changes, at the admin surface.** A staff user who is neither
role `ADMIN` nor a superuser can no longer retry an asset from the admin
action, and sees *"not an asset you may manage"*. This matches the privilege
definition already used in `entitlements/permissions.py`, `catalog/selectors.py`,
`media_assets/services.py` and `entitlements/resolver.py` — `Role.ADMIN or
is_superuser` — so it narrows one surface to the rule the rest of the codebase
already applies. No account in the repository's fixtures or seeds is in that
position; whether any real operator account is, is for the owner to confirm
when admin accounts are provisioned.

**Nothing else changes.** No API contract, status code, response body, model,
migration, dependency or cost. Every refusal that was a 404 is still a 404, by
the same reasoning (§6.3) from a different mechanism, and the OpenAPI schema is
byte-identical.

## Every `except NotYours` in these views is now a divergence guard

Scoping a read makes that view's own `except NotYours` dead: the scoped
`get_object_or_404` already refuses anyone the service would, and the
equivalence tests above prove the two cannot disagree. Coverage found the
first one; reading the code did not.

**This section was written in the singular and that was wrong.** It described
the retry view's handler while the same batch scoped three more reads —
`MediaAssetCompleteView`, `SegmentEditView` and `TranscriptReviewView` — each
of which has a handler in exactly the same position. A reviewer measured them
as uncovered. Documenting one and leaving three indistinguishable from
leftovers is worse than either rule applied consistently, so the rule is
stated once, here:

> In `media_assets.views`, `transcripts.views` and the `retry_failed` admin
> action, an `except NotYours` is kept **even where the scope filter makes it
> unreachable**, because the state it handles is the one the equivalence tests
> forbid: a scope filter that grew broader than its predicate. Without the
> handler that divergence is an unhandled exception and a 500; with it, the
> refusal the service still correctly makes reaches the caller as the 404 it
> should be. They are not leftovers and should not be deleted as dead code.

Two tests reach that state by widening a selector —
`test_a_divergent_scope_is_a_404_rather_than_a_500` for the retry view and
`test_a_divergent_admin_scope_warns_rather_than_500s` for the admin action —
so the branch is measured rather than asserted. The others are the same
mechanism and are covered by the rule rather than by a test each; one more
patching test per handler would assert the same thing four times.

`LessonUploadUrlView` is the exception that proves the rule: its lesson is
still fetched from `Lesson.objects` unscoped, so **its handler is live**. A
`lessons_manageable_by` selector would scope it, and `lessons_visible_to` is
the wrong rule for the job — it admits other instructors' published lessons.
Left for whoever needs it.

## What this does not cover

**`SegmentEditView` was the one exception this ADR first carried, and it is now
closed** — `segments_editable_by` scopes it, and `edit_segment` keeps its own
guard. The deferral is recorded rather than deleted because the reasoning is
worth keeping: a read that is safe only because of the write that follows it is
one refactor away from not being, which is the argument for scoping it even
where the outcome was never wrong.

**Still open, and deliberately not touched here:** the admin site gates on
`is_staff` plus a second factor (`core/admin_site.py`), not on `Role.ADMIN`, so
model permissions are what separate operators on every *other* registered
model. `MediaAssetAdmin` is scoped because this batch is about media and
transcripts; `WebhookEventAdmin` and the rest are not reviewed here. Whether
the admin should require `Role.ADMIN` outright is a change to the admin access
strategy and belongs to the owner under §5, not to a repair batch.
