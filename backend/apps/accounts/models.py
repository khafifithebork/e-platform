"""Accounts.

The custom User model. `architecture.md` §10 M2 is emphatic about this and it
is worth repeating: the first migration applied to any database fixes
AUTH_USER_MODEL permanently. Changing it afterwards means renaming a table by
hand, rewriting the migration graph, and repointing every foreign key in the
schema. The `make migrate` guard added in M0 has been refusing ever since
precisely so this model could land first.
"""

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.managers import UserManager
from apps.core.models import TimestampedModel, UUIDPrimaryKeyModel


class Role(models.TextChoices):
    """The three roles from architecture.md §4.4.

    Role alone never authorises anything — §4.4 requires an object-level check
    as well. It answers "who is asking", not "may they touch this row".
    """

    STUDENT = "STUDENT", "Student"
    INSTRUCTOR = "INSTRUCTOR", "Instructor"
    ADMIN = "ADMIN", "Admin"


class User(UUIDPrimaryKeyModel, AbstractBaseUser, PermissionsMixin):
    """A person with an account.

    ``PermissionsMixin`` is included because Django Admin needs ``is_staff``
    and the permission machinery, and §6.2 leans on Django Admin for most
    administrative CRUD. The project's own authorisation is the ``role`` field
    plus object-level checks; the Django permission tables are not used for
    product logic.
    """

    email = models.EmailField(
        unique=True,
        help_text="Login identity. Stored lowercased; see the Meta constraint.",
    )

    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.STUDENT,
        help_text=(
            "Never writable from a request body. Instructor and admin are granted, never claimed."
        ),
    )

    is_email_verified = models.BooleanField(
        default=False,
        help_text=(
            "Verified addresses are required before starting a trial (§7.1), "
            "not before logging in — ADR-005 section 2.3."
        ),
    )

    # Required by Django Admin. Distinct from `role`: a STUDENT is never staff,
    # but an ADMIN is not automatically staff either — that is granted.
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    date_joined = models.DateTimeField(default=timezone.now, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    # Deliberately empty. REQUIRED_FIELDS lists what `createsuperuser` should
    # prompt for *in addition to* USERNAME_FIELD; including email there makes
    # it ask twice.
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        constraints: ClassVar[list] = [
            # ADR-005 §2.2. architecture.md §5.2 specified citext, which Django
            # 5.x removed. This keeps the guarantee in the database rather than
            # only in the manager (invariant 11) — the manager lowercases, but
            # a bulk insert or a raw query bypasses it and this does not.
            #
            # The field also carries unique=True, which looks redundant and is
            # not: Django's auth.E003 check requires USERNAME_FIELD to have a
            # field-level unique, and an expression constraint does not satisfy
            # it. Two indexes, deliberately.
            models.UniqueConstraint(
                Lower("email"),
                name="user_email_case_insensitive_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.email


class StudentProfile(UUIDPrimaryKeyModel, TimestampedModel):
    """Learner-facing profile, created with the account (ADR-005 §2.4).

    Eagerly rather than lazily: a user without a profile would be a null check
    in every consumer, forever, to save one row at signup.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    display_name = models.CharField(max_length=100, blank=True)

    # target_language, current_level, learning_goal, timezone and ui_locale
    # (§5.1) arrive with the catalogue in M3, when Language exists to point at.

    def __str__(self) -> str:
        return f"Student profile for {self.user.email}"


class InstructorProfile(UUIDPrimaryKeyModel, TimestampedModel):
    """Instructor profile.

    Existing is not the same as being approved. `approved_at` stays null until
    an admin approves the instructor, and the approval workflow itself is M10 —
    §6.2 puts the review queue there. Nothing should treat the presence of this
    row as authorisation.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="instructor_profile",
    )
    headline = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)

    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        # PROTECT, not CASCADE: deleting an admin must not silently erase the
        # record of who approved an instructor. §5.4 makes this the rule for
        # anything with an audit character.
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="instructors_approved",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"Instructor profile for {self.user.email}"
