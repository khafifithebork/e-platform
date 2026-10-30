"""Who counts as a platform administrator, and who is signed in at all.

Two predicates, in one place, because they were in seven. Both were written
inline at every call site that needed them — `media_assets.services.may_manage`,
`catalog.selectors.lessons_visible_to`, `entitlements.resolver`,
`entitlements.permissions.IsAdministrator` and the three content selectors added
with ADR-040 — and a review of that ADR's batch pointed out that naming one
privilege definition in prose while leaving it with no implementation is how it
drifts.

**It already had drifted.** `catalog.services` requires `by.role == Role.ADMIN`
with no superuser clause, so a superuser can scope media and transcripts but
cannot approve a course. Nothing records that as intentional and nothing pins
the two together. It is left alone here deliberately: changing it would grant
superusers a publication power they do not have today, which is a privilege
decision and the owner's under §5, not a cleanup's.

A free function rather than a method on ``User``, because every caller may be
handed ``AnonymousUser`` — which is why the attribute reads go through
``getattr``.
"""

from __future__ import annotations

from apps.accounts.models import Role


def is_signed_in(user) -> bool:
    """Whether there is an authenticated user here at all.

    ``None`` as well as ``AnonymousUser``: a service called outside a request
    may legitimately have no user, and a scope filter must answer "nothing"
    for both rather than raise.
    """
    return user is not None and bool(getattr(user, "is_authenticated", False))


def is_platform_administrator(user) -> bool:
    """Whether this person administers content they do not own.

    Role **or** ``is_superuser``, which is the pair the rest of the codebase
    already treats as one answer. A superuser without the role is a bootstrap
    account and locking it out of its own admin surface is the kind of
    sharp edge nobody finds until the first production incident.

    Deliberately *not* ``is_staff``: that is independent of ``Role``
    (``accounts.models``), and an operator holding a model permission is not
    the same as someone entitled to another instructor's content. Treating the
    two as equivalent is the hole ADR-040 was written about.
    """
    return getattr(user, "role", None) == Role.ADMIN or bool(getattr(user, "is_superuser", False))


__all__ = ["is_platform_administrator", "is_signed_in"]
