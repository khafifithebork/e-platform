"""The DRF wiring between a view and the resolver.

Invariant 2: this is an HTTP concern and holds no business logic. It decides
nothing — it asks ``resolve_access`` and translates the answer. Every access
rule stays in one function, which is invariant 3.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.entitlements.exceptions import EntitlementDenied
from apps.entitlements.resolver import resolve_access


class IsEntitledToLesson(BasePermission):
    """Allow a lesson through only if the resolver says so.

    **Raises rather than returning False**, and that is the substance of this
    class rather than a detail. A permission returning False produces DRF's
    generic 403 with no reason, so the frontend would have to work out for
    itself whether to offer signing in, subscribing or updating a card — which
    is entitlement logic in a second place, disagreeing with the first the day
    one of them changes.

    Object-level only. ``has_permission`` deliberately does not gate on being
    signed in: preview lessons are readable by anonymous visitors, and a
    blanket authentication check here would deny them before the resolver ever
    saw the lesson. The view still needs ``AllowAny`` for that to hold, and a
    test asserts it.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        decision = resolve_access(user=request.user, lesson=obj)

        if not decision.allowed:
            raise EntitlementDenied(decision)

        return True
