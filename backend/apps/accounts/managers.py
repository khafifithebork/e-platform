"""User creation.

Django's default manager is built around a username field. This one is built
around an email address, and normalises it on the way in so that the stored
form is always the canonical one.
"""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Creates users identified by email rather than username."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")

        # Two separate normalisations. Django's own lowercases the domain only,
        # because the local part is technically case-sensitive per RFC 5321.
        # In practice no provider treats it that way, and honouring the RFC
        # here would mean User@x.com and user@x.com are different accounts —
        # which is a support burden and an account-takeover confusion, not a
        # feature. ADR-005 section 2.2.
        email = self.normalize_email(email).lower()

        user = self.model(email=email, **extra_fields)
        # set_password hashes with the configured hasher. The plaintext is
        # never assigned to the field.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        # Asserted rather than silently corrected: a caller passing
        # is_staff=False to create_superuser has misunderstood something, and
        # quietly overriding them hides it.
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)
