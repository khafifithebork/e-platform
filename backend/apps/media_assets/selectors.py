"""Media reads, scoped to whoever may manage the lesson (invariant 10).

A ``MediaAsset`` is addressed by its own id, with no course in the path to
scope it by. architecture.md §4.4 calls exactly that the commonest IDOR in a
DRF codebase, and the answer invariant 10 gives is the scope filter rather
than a fetch followed by a check: a filter cannot be forgotten by the next
caller, and a view that has to remember a second step eventually meets someone
who does not.
"""

from __future__ import annotations

from apps.accounts.privileges import is_platform_administrator, is_signed_in
from apps.media_assets.models import MediaAsset


def assets_manageable_by(*, user):
    """Every asset this person may manage, and nothing else.

    The same rule as ``services.may_manage``, expressed as a queryset because
    that is the form a view can be handed. Two expressions of one rule is the
    drift ``transcripts.services.may_review`` warns about, so
    ``TestTheScopeFilterAndTheObjectCheckAgree`` asserts the two answer
    identically across every role — the duplication is pinned rather than
    trusted.

    Not the entitlement resolver, deliberately: that decides who may *watch*
    (invariant 3). This decides who may *replace*, and merging them would let
    every subscriber overwrite an instructor's master.
    """
    if not is_signed_in(user):
        return MediaAsset.objects.none()

    if is_platform_administrator(user):
        manageable = MediaAsset.objects.all()
    else:
        manageable = MediaAsset.objects.filter(lesson__course__instructor=user)

    # Joined for the services, not for the serializer — and the first version
    # of this comment said the opposite. `MediaAssetSerializer` emits `lesson`
    # as a primary key and the view no longer calls `may_manage`, so the status
    # response needs neither join. `complete_upload` and `retry_processing` do:
    # both read `asset.lesson` and `may_manage` walks it to the course. Keeping
    # it costs one join on a single-row read and saves a round trip on every
    # write (ADR-009 — measured, and re-measured when a reviewer pointed out
    # the stated reason had stopped being true).
    return manageable.select_related("lesson__course")


__all__ = ["assets_manageable_by"]
