"""The DRF wiring between a view and the resolver.

Invariant 2: this is an HTTP concern and holds no business logic. It decides
nothing — it asks ``resolve_access`` and translates the answer. Every access
rule stays in one function, which is invariant 3.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role
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


class IsAdministrator(BasePermission):
    """Only this product's administrators.

    ``role == ADMIN``, not ``is_staff``. M3 established that these are
    different facts: staff is Django's flag for reaching the admin site, and
    the day someone is given it to fix a typo must not be the day they can
    read every subscriber's billing history.

    ``is_superuser`` is accepted alongside it, because a superuser can grant
    itself the role anyway and pretending otherwise is theatre.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return getattr(user, "role", None) == Role.ADMIN or user.is_superuser
