"""Account reads.

Invariant 2: queries live here, not in views or serializers.
"""

from apps.accounts.models import User


def get_user_for_me(*, user: User) -> User:
    """Re-read the signed-in user with their profile joined.

    The join does not save a query over reading ``request.user.student_profile``
    lazily — both cost one beyond what the authentication middleware already
    did. It is here for layering (invariant 2, reads live in selectors) and
    because it stays a single query as more relations are added to this
    response, which is what stops /auth/me/ fanning out later.
    """
    return User.objects.select_related("student_profile").get(pk=user.pk)
