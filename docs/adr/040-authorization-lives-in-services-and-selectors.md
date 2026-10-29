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

The cost is provider minutes and a pipeline run on content the caller has no
claim on. It is not a data-disclosure hole: the admin action returns no asset
data, and the API surface was correctly guarded throughout.

## Decision

**1. Object reads are scoped in the queryset.** `media_assets.selectors
.assets_manageable_by(user)` and `transcripts.selectors
.transcripts_reviewable_by(user)` return what the caller may touch.
`transcript_for_review` now requires `user` — a required argument rather than
an optional one, because an optional scope is the one the next caller forgets.
Views call `get_object_or_404` against the scoped queryset and branch on
absence only.

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

## One handler is deliberately unreachable

Scoping the retry view made its own `except NotYours` dead: the scoped
`get_object_or_404` already refuses anyone the service would, and the
equivalence tests above prove the two cannot disagree. Coverage found it; it
was not noticed by reading.

It is kept rather than deleted, because the state it handles is precisely the
one those tests forbid — a scope filter that grew broader than `may_manage`.
Without the handler that divergence surfaces as an unhandled exception and a
500; with it, the refusal the service still makes reaches the caller as a 404.
`test_a_divergent_scope_is_a_404_rather_than_a_500` widens the selector to
reach the line, so the branch is measured rather than asserted and the reason
it exists is written down next to it.

## What this does not cover

`SegmentEditView` still fetches `TranscriptSegment` from an unscoped manager
before handing it to `edit_segment`, which raises `NotYours`. The decision is
in the service, so invariant 2 holds and the outcome is right; the fetch is
unscoped against the letter of invariant 10. It is left alone deliberately —
this batch was scoped to the paths where the decision itself sat in the wrong
layer, and widening it would have put the change over §9's file budget. Worth a
separate look.
