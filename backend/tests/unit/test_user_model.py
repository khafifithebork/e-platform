"""The custom User model.

This is the most order-sensitive model in the project. The first migration
applied to any database fixes AUTH_USER_MODEL permanently, and changing it
afterwards is a manual table rename plus a hand-written migration-graph rewrite
plus every foreign key repointed (`architecture.md` §10, M2). The `make migrate`
guard has been refusing since M0 to protect this moment.

The security-relevant assertions here are the ones about `role`. A client that
can set its own role owns the platform, so that field is tested from several
directions.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower

User = get_user_model()


class TestModelIsWiredUp:
    def test_auth_user_model_points_at_accounts(self) -> None:
        from django.conf import settings

        assert settings.AUTH_USER_MODEL == "accounts.User"

    def test_email_is_the_login_field(self) -> None:
        assert User.USERNAME_FIELD == "email"

    def test_there_is_no_username(self) -> None:
        """Email is the identity. A username would be a second one."""
        assert not hasattr(User, "username")

    def test_email_is_not_also_required_separately(self) -> None:
        """REQUIRED_FIELDS is for createsuperuser prompts *besides* the
        username field; listing email there makes the command ask twice."""
        assert "email" not in User.REQUIRED_FIELDS


class TestPrimaryKey:
    def test_is_a_uuid(self) -> None:
        """architecture.md §5.2: sequential ids in URLs leak business
        information and make enumeration trivial."""
        pk = User._meta.get_field("id")

        assert pk.primary_key is True
        assert pk.get_internal_type() == "UUIDField"

    def test_defaults_to_a_generated_value(self) -> None:
        generated = User._meta.get_field("id").get_default()

        assert isinstance(generated, uuid.UUID)


class TestRoleCannotBeSelfAssigned:
    """The highest-value field on the model.

    Nothing in a request body may reach it. These tests pin the model half;
    the serializer half is tested when registration exists.
    """

    def test_the_three_roles_are_the_only_choices(self) -> None:
        choices = {value for value, _ in User._meta.get_field("role").choices}

        assert choices == {"STUDENT", "INSTRUCTOR", "ADMIN"}

    def test_new_accounts_are_students(self) -> None:
        """Instructor and admin are granted, never claimed."""
        assert User._meta.get_field("role").default == "STUDENT"

    def test_email_starts_unverified(self) -> None:
        assert User._meta.get_field("is_email_verified").default is False


@pytest.mark.django_db
class TestUserCreation:
    def test_creates_a_student_by_default(self) -> None:
        user = User.objects.create_user(email="learner@example.test", password="pw-not-a-secret")

        assert user.role == "STUDENT"
        assert user.is_email_verified is False
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_password_is_hashed_not_stored(self) -> None:
        user = User.objects.create_user(email="a@example.test", password="pw-not-a-secret")

        assert user.password != "pw-not-a-secret"
        assert user.check_password("pw-not-a-secret") is True

    def test_email_is_required(self) -> None:
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="pw-not-a-secret")

    def test_superuser_gets_staff_and_superuser_flags(self) -> None:
        admin = User.objects.create_superuser(email="root@example.test", password="pw")

        assert admin.is_staff is True
        assert admin.is_superuser is True


@pytest.mark.django_db
class TestEmailIsCaseInsensitive:
    """ADR-005 §2.2. `User@x.com` and `user@x.com` are one person.

    architecture.md §5.2 specified citext, which Django 5.x removed; the
    guarantee moved to a functional unique constraint so it still lives in the
    database rather than only in a Python validator (invariant 11).
    """

    def test_stored_lowercased(self) -> None:
        user = User.objects.create_user(email="Mixed.Case@Example.TEST", password="pw")

        assert user.email == "mixed.case@example.test"

    def test_a_differently_cased_duplicate_is_rejected_by_the_database(self) -> None:
        User.objects.create_user(email="dup@example.test", password="pw")

        # Bypasses the manager deliberately: the point is that the *database*
        # refuses, not that the manager remembered to lowercase.
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(email="DUP@EXAMPLE.TEST", password="x")

    def test_the_constraint_is_on_the_lowercased_column(self) -> None:
        names = {
            constraint.name
            for constraint in User._meta.constraints
            if getattr(constraint, "expressions", None)
            and any(isinstance(e, Lower) for e in constraint.expressions)
        }

        assert names, "expected a UniqueConstraint on Lower(email)"

    def test_lookup_by_any_casing_finds_the_account(self) -> None:
        User.objects.create_user(email="finder@example.test", password="pw")

        assert User.objects.filter(email__iexact="FINDER@EXAMPLE.TEST").exists()
