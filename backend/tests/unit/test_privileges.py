"""The two privilege predicates, which were seven inline copies.

Tested once, here, rather than six times per call site: the content selectors
are pinned to `may_manage`/`may_review` by their own equivalence classes, and
those now share this expression, so this is the one place the rule itself is
asserted.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import Role
from apps.accounts.privileges import is_platform_administrator, is_signed_in

pytestmark = pytest.mark.django_db

PASSWORD = "a-long-enough-passphrase"


def _user(email: str, role: str = Role.STUDENT, **flags):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    for field, value in flags.items():
        setattr(user, field, value)
    user.save(update_fields=["role", *flags])
    return user


class TestIsSignedIn:
    def test_a_real_user_is(self) -> None:
        assert is_signed_in(_user("someone@example.test")) is True

    def test_anonymous_is_not(self) -> None:
        assert is_signed_in(AnonymousUser()) is False

    def test_none_is_not(self) -> None:
        """A service called outside a request may genuinely have no user, and
        a scope filter must answer "nothing" rather than raise."""
        assert is_signed_in(None) is False


class TestIsPlatformAdministrator:
    def test_the_admin_role_counts(self) -> None:
        assert is_platform_administrator(_user("boss@example.test", Role.ADMIN)) is True

    def test_a_superuser_counts_without_the_role(self) -> None:
        """A bootstrap account locked out of its own admin surface is the kind
        of sharp edge nobody finds until the first incident."""
        root = _user("root@example.test", Role.STUDENT, is_superuser=True)

        assert is_platform_administrator(root) is True

    def test_an_instructor_does_not(self) -> None:
        assert is_platform_administrator(_user("teacher@example.test", Role.INSTRUCTOR)) is False

    def test_a_student_does_not(self) -> None:
        assert is_platform_administrator(_user("learner@example.test")) is False

    def test_staff_alone_does_not(self) -> None:
        """`is_staff` is independent of `Role`, and an operator holding a model
        permission is not someone entitled to another instructor's content.
        Treating the two as equivalent is the hole ADR-040 was written about.
        """
        operator = _user("ops@example.test", Role.STUDENT, is_staff=True)

        assert is_platform_administrator(operator) is False

    def test_anonymous_does_not_and_does_not_raise(self) -> None:
        """Every caller may be handed `AnonymousUser`, which is why the
        attribute reads go through `getattr`."""
        assert is_platform_administrator(AnonymousUser()) is False

    def test_none_does_not_and_does_not_raise(self) -> None:
        assert is_platform_administrator(None) is False
