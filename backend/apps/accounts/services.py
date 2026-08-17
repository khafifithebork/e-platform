"""Account writes.

Invariant 2: business operations live here, not in serializers. A serializer
runs only in an HTTP context, which means the same operation would be
unavailable to a management command, a Celery task or a test — and the second
implementation someone writes for those will drift from the first.
"""

import hashlib
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, StudentProfile, User

# 32 bytes of entropy, URL-safe. Long enough that guessing is not a strategy —
# unlike login, a token endpoint has no account to lock out, so brute-force
# resistance has to come from the token itself.
VERIFICATION_TOKEN_BYTES = 32

# Long enough to survive a spam folder and a night's sleep; short enough that a
# link forwarded months later is not still a working credential.
VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)


class EmailAlreadyRegistered(Exception):
    """Raised instead of letting the database error escape.

    Deliberately not an ``IntegrityError`` subclass. A raw one reaching a view
    produces a 500, and in DEBUG an error page naming the constraint that
    failed — which tells an attacker both that the address is registered and
    how uniqueness is enforced.

    Callers must also decide what to *say*. Registration must not reveal that
    an address is taken (§7.1 account enumeration), so the endpoint answers
    identically whether this was raised or not.
    """


@transaction.atomic
def create_account(*, email: str, password: str) -> User:
    """Create a user and their student profile.

    Keyword-only, and with no ``role`` parameter. That is the point rather than
    an accident: the strongest form of "role is not writable by a client" is
    that there is no argument to pass it through. Instructor and admin are
    granted later by an administrator, never claimed at registration.

    Atomic, so a failure part-way leaves no account without a profile. A user
    with no profile would be a null check in every consumer forever — and would
    be created by exactly the kind of transient failure nobody reproduces.
    """
    try:
        # The manager lowercases the address; the database constraint on
        # Lower(email) is what actually enforces uniqueness (ADR-005 §2.2).
        user = User.objects.create_user(email=email, password=password)
    except IntegrityError as exc:
        raise EmailAlreadyRegistered(email) from exc

    # Students only. An instructor profile appears when an admin grants the
    # role, which is M10 — its presence is not authorisation either way.
    StudentProfile.objects.create(user=user)

    return user


class InvalidVerificationToken(Exception):
    """Unknown, expired, or already consumed.

    One exception for all three on purpose. Distinguishing them tells a caller
    holding a guessed token whether it ever existed, which turns a failed guess
    into information.
    """


def _hash_token(raw: str) -> str:
    """SHA-256 of the raw token.

    A plain hash rather than a password hasher, and the difference matters:
    Argon2 is slow by design to make guessing a low-entropy human password
    expensive. This token carries 256 bits of entropy from a CSPRNG, so there
    is nothing to guess, and a deliberately slow hash on every verification
    request would only be a denial-of-service surface.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_email_verification(*, user: User) -> str:
    """Create a token and return the raw value, which is never stored.

    The caller emails it. Once this returns, the raw token cannot be recovered
    from the database — losing it means issuing another.
    """
    raw = secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)

    EmailVerificationToken.objects.create(
        user=user,
        token_hash=_hash_token(raw),
        expires_at=timezone.now() + VERIFICATION_TOKEN_LIFETIME,
    )

    return raw


@transaction.atomic
def verify_email(*, token: str) -> User:
    """Consume a token and mark the account verified.

    Atomic and consumed by a locked read, so two requests racing the same link
    cannot both succeed. That matters less for verification than it will for
    password reset, but the pattern should be the same in both.
    """
    if not token:
        # Short-circuit: hashing the empty string produces a real digest, and
        # a stored row could otherwise be matched by sending nothing at all.
        raise InvalidVerificationToken

    try:
        record = EmailVerificationToken.objects.select_for_update().get(
            token_hash=_hash_token(token)
        )
    except EmailVerificationToken.DoesNotExist as exc:
        raise InvalidVerificationToken from exc

    if record.consumed_at is not None:
        raise InvalidVerificationToken
    if record.expires_at <= timezone.now():
        raise InvalidVerificationToken

    record.consumed_at = timezone.now()
    record.save(update_fields=["consumed_at", "updated_at"])

    user = record.user
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])

    return user
