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


class EmailOnlySerializer(serializers.Serializer):
    """For resending a verification email."""

    email = serializers.EmailField(max_length=254)


class VerifyEmailSerializer(serializers.Serializer):
    """For consuming a verification token."""

    token = serializers.CharField(max_length=256, trim_whitespace=True)
