"""I/O shape only.

Invariant 2: format validation lives here, business rules do not. Everything
these classes do is check that the request *looks* right; whether the operation
is permitted, and what it does, belongs in services.py.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    """Registration input.

    Two fields, and that is the security control. DRF ignores fields it does
    not declare, so `role`, `is_staff` and `is_superuser` in a request body go
    nowhere — there is no path from here to them. Abuse case 3.
    """

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True,
        max_length=128,
        style={"input_type": "password"},
    )

    def validate_password(self, value: str) -> str:
        """Django's configured validators — length, common passwords, numeric.

        Raised as a DRF error so it reaches the client through the Problem
        Details handler with the field name attached, rather than as a 500.
        """
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class LoginSerializer(serializers.Serializer):
    """Login input.

    No password validators here. They exist to stop weak passwords being
    *chosen*; applying them at login would reject a valid credential set before
    a stricter policy, and would leak the policy to anyone probing.
    """

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True,
        max_length=128,
        style={"input_type": "password"},
    )


class EmailOnlySerializer(serializers.Serializer):
    """For resending a verification email."""

    email = serializers.EmailField(max_length=254)


class VerifyEmailSerializer(serializers.Serializer):
    """For consuming a verification token."""

    token = serializers.CharField(max_length=256, trim_whitespace=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Consume a reset token and set a new password."""

    token = serializers.CharField(max_length=256, trim_whitespace=True)
    new_password = serializers.CharField(
        write_only=True, max_length=128, style={"input_type": "password"}
    )

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """Change a signed-in user's password.

    The current password is required even though the caller is authenticated —
    a session left open on a shared machine is exactly what this stops.
    """

    current_password = serializers.CharField(
        write_only=True, max_length=128, style={"input_type": "password"}
    )
    new_password = serializers.CharField(
        write_only=True, max_length=128, style={"input_type": "password"}
    )

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class StudentProfileSerializer(serializers.Serializer):
    """Output only."""

    display_name = serializers.CharField()


class MeSerializer(serializers.Serializer):
    """The signed-in user.

    A field allowlist rather than a ModelSerializer with `exclude`. With
    `exclude`, every field added to User later is exposed by default and
    somebody has to remember to hide it; here the default is that new fields
    stay private until named.

    `is_staff`, `is_superuser`, `groups` and `user_permissions` are therefore
    absent: they are internal authorisation detail, and the frontend branches
    on `role`.

    No `access` object until M4 (architecture.md section 6.2). Adding an
    optional object later is backward compatible; shipping a fake one now would
    invite the frontend to depend on a shape with no logic behind it.
    """

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_email_verified = serializers.BooleanField(read_only=True)
    profile = StudentProfileSerializer(source="student_profile", read_only=True)
