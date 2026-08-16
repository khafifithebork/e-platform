"""Account writes.

Invariant 2: business operations live here, not in serializers. A serializer
runs only in an HTTP context, which means the same operation would be
unavailable to a management command, a Celery task or a test — and the second
implementation someone writes for those will drift from the first.
"""

from django.db import IntegrityError, transaction

from apps.accounts.models import StudentProfile, User


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
