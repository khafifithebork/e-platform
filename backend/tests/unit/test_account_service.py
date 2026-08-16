"""Account creation.

The write that every other account operation is built on. Invariant 2 puts it
in ``services.py`` so it is callable from a view, a management command, a
Celery task or a test — the DRF failure mode this project is explicitly
avoiding is the same logic living in a serializer, where only an HTTP request
can reach it.

The `role` assertions matter most. A client that can choose its own role owns
the platform, so the service simply has no parameter for it.
"""

from __future__ import annotations

import inspect
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


@pytest.mark.django_db
class TestCreateAccount:
    def test_creates_a_student(self) -> None:
        from apps.accounts.services import create_account

        user = create_account(email="learner@example.test", password="pw-for-this-test")

        assert user.pk is not None
        assert user.role == "STUDENT"
        assert user.is_email_verified is False

    def test_creates_the_profile_alongside_the_user(self) -> None:
        """ADR-005 §2.4: eagerly, so no consumer ever has to null-check it."""
        from apps.accounts.models import StudentProfile
        from apps.accounts.services import create_account

        user = create_account(email="learner@example.test", password="pw-for-this-test")

        assert StudentProfile.objects.filter(user=user).exists()
        assert user.student_profile is not None

    def test_does_not_create_an_instructor_profile(self) -> None:
        """Instructor is granted, never claimed. The profile appears when an
        admin grants the role, which is M10."""
        from apps.accounts.models import InstructorProfile
        from apps.accounts.services import create_account

        create_account(email="learner@example.test", password="pw-for-this-test")

        assert not InstructorProfile.objects.exists()

    def test_the_password_is_hashed(self) -> None:
        from apps.accounts.services import create_account

        user = create_account(email="learner@example.test", password="pw-for-this-test")

        assert user.password != "pw-for-this-test"
        assert user.check_password("pw-for-this-test")

    def test_the_email_is_normalised(self) -> None:
        from apps.accounts.services import create_account

        user = create_account(email="Mixed.Case@Example.TEST", password="pw-for-this-test")

        assert user.email == "mixed.case@example.test"


class TestRoleIsNotAnArgument:
    """The strongest form of "not writable" is "not expressible"."""

    def test_the_signature_has_no_role_parameter(self) -> None:
        from apps.accounts.services import create_account

        assert "role" not in inspect.signature(create_account).parameters

    def test_arguments_are_keyword_only(self) -> None:
        """Positional arguments invite create_account(email, password, "ADMIN")
        to be added later without anyone noticing at the call sites."""
        from apps.accounts.services import create_account

        kinds = {p.kind for p in inspect.signature(create_account).parameters.values()}

        assert kinds == {inspect.Parameter.KEYWORD_ONLY}


@pytest.mark.django_db
class TestDuplicateEmail:
    def test_a_duplicate_is_refused(self) -> None:
        from apps.accounts.services import EmailAlreadyRegistered, create_account

        create_account(email="taken@example.test", password="pw-for-this-test")

        with pytest.raises(EmailAlreadyRegistered):
            create_account(email="taken@example.test", password="pw-for-this-test")

    def test_a_differently_cased_duplicate_is_refused(self) -> None:
        from apps.accounts.services import EmailAlreadyRegistered, create_account

        create_account(email="taken@example.test", password="pw-for-this-test")

        with pytest.raises(EmailAlreadyRegistered):
            create_account(email="TAKEN@EXAMPLE.TEST", password="pw-for-this-test")

    def test_the_first_account_survives_the_refusal(self) -> None:
        """The rollback must not take the existing user with it."""
        from apps.accounts.services import EmailAlreadyRegistered, create_account

        create_account(email="taken@example.test", password="pw-for-this-test")

        with pytest.raises(EmailAlreadyRegistered):
            create_account(email="taken@example.test", password="other-pw")

        assert User.objects.filter(email="taken@example.test").count() == 1

    def test_the_domain_error_does_not_leak_the_database_error(self) -> None:
        """A raw IntegrityError reaching a view would produce a 500 and, in
        DEBUG, an error page naming the constraint."""
        from apps.accounts.services import EmailAlreadyRegistered

        assert not issubclass(EmailAlreadyRegistered, IntegrityError)


@pytest.mark.django_db
class TestAtomicity:
    def test_a_failure_creating_the_profile_leaves_no_user(self) -> None:
        """User and profile are one write or neither.

        The failure is injected rather than asserted-upon: this is testing that
        the transaction rolls back, not that some collaborator was called.
        """
        from apps.accounts import services

        with (
            mock.patch.object(
                services.StudentProfile.objects,
                "create",
                side_effect=RuntimeError("disk on fire"),
            ),
            pytest.raises(RuntimeError),
        ):
            services.create_account(email="doomed@example.test", password="pw-for-this-test")

        assert not User.objects.filter(email="doomed@example.test").exists()
