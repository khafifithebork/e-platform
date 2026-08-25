"""Account reads.

Invariant 2: queries live here, not in views or serializers.
"""

from apps.accounts.models import Role, User


def get_user_for_me(*, user: User) -> User:
    """Re-read the signed-in user with their profile joined.

    The join does not save a query over reading ``request.user.student_profile``
    lazily — both cost one beyond what the authentication middleware already
    did. It is here for layering (invariant 2, reads live in selectors) and
    because it stays a single query as more relations are added to this
    response, which is what stops /auth/me/ fanning out later.
    """
    return User.objects.select_related("student_profile").get(pk=user.pk)


def administrator_emails() -> list[str]:
    """Everyone who should hear that a course needs reviewing.

    A selector rather than a queryset built inside the notifying service, so
    "who is an administrator" stays one answer. Returns addresses rather than
    users because that is all the caller may have — handing a service a `User`
    invites it to read something else off them.
    """
    return list(
        User.objects.filter(role=Role.ADMIN, is_active=True)
        .order_by("email")
        .values_list("email", flat=True)
    )
