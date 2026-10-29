"""Media reads, scoped to whoever may manage the lesson (invariant 10).

A ``MediaAsset`` is addressed by its own id, with no course in the path to
scope it by. architecture.md §4.4 calls exactly that the commonest IDOR in a
DRF codebase, and the answer invariant 10 gives is the scope filter rather
than a fetch followed by a check: a filter cannot be forgotten by the next
caller, and a view that has to remember a second step eventually meets someone
who does not.
"""

from __future__ import annotations

from apps.accounts.models import Role
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
    if user is None or not getattr(user, "is_authenticated", False):
        return MediaAsset.objects.none()

    if getattr(user, "role", None) == Role.ADMIN or getattr(user, "is_superuser", False):
        manageable = MediaAsset.objects.all()
    else:
        manageable = MediaAsset.objects.filter(lesson__course__instructor=user)

    # Joined rather than left for the serializer to dereference: the status
    # response renders the lesson, and `may_manage` reads `lesson.course`
    # (ADR-009 — do not pay for a round trip you can fold into the join).
    return manageable.select_related("lesson__course")


__all__ = ["assets_manageable_by"]
