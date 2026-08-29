"""I/O shape only.

Invariant 2: format validation lives here, business rules do not. Everything
these classes do is check that the request *looks* right; whether the operation
is permitted, and what it does, belongs in services.py.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.entitlements.resolver import Cta, Reason


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


class AccessSerializer(serializers.Serializer):
    """The entitlement decision, as the frontend receives it.

    Declared as a serializer purely so the OpenAPI schema describes the shape
    and invariant 16's generated types are real rather than `unknown`. Nothing
    constructs it — the resolver produces the values.
    """

    allowed = serializers.BooleanField(read_only=True)
    # ChoiceField, not CharField: drf-spectacular turns choices into a schema
    # enum, which openapi-typescript turns into a union the frontend can be
    # exhaustive over. As a bare string the set lived in two places and drifted.
    reason = serializers.ChoiceField(choices=Reason.choices, read_only=True)
    cta = serializers.ChoiceField(choices=Cta.CHOICES, read_only=True, allow_null=True)


class MeSerializer(serializers.Serializer):
    """The signed-in user.

    A field allowlist rather than a ModelSerializer with `exclude`. With
    `exclude`, every field added to User later is exposed by default and
    somebody has to remember to hide it; here the default is that new fields
    stay private until named.

    `is_staff`, `is_superuser`, `groups` and `user_permissions` are therefore
    absent: they are internal authorisation detail, and the frontend branches
    on `role`.

    `access` carries the entitlement decision, as architecture.md section 6.2
    requires, "so the frontend never re-derives access rules". It is the same
    resolver the gated endpoints use — `resolve_account_access` is the
    lesson-independent half of `resolve_access`, not a second copy, because two
    implementations of these rules disagree the day one of them changes
    (invariant 3).

    A reason and a call to action, never a bare boolean: the interface has to
    tell "start a trial" from "your card failed", and a boolean would put that
    inference in the frontend.
    """

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_email_verified = serializers.BooleanField(read_only=True)
    profile = StudentProfileSerializer(source="student_profile", read_only=True)
    access = serializers.SerializerMethodField()

    @extend_schema_field(AccessSerializer)
    def get_access(self, user) -> dict:
        # Imported here rather than at module scope: accounts is the lower
        # layer and entitlements already depends on it, so a top-level import
        # would tie the two together in both directions.
        from apps.entitlements.resolver import resolve_account_access

        decision = resolve_account_access(user=user)
        return {
            "allowed": decision.allowed,
            "reason": str(decision.reason),
            "cta": decision.cta,
        }
