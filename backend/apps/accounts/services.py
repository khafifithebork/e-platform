"""Account writes.

Invariant 2: business operations live here, not in serializers. A serializer
runs only in an HTTP context, which means the same operation would be
unavailable to a management command, a Celery task or a test — and the second
implementation someone writes for those will drift from the first.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.models import (
    BetaInvitation,
    EmailVerificationToken,
    PasswordResetToken,
    Role,
    StudentProfile,
    User,
)
from apps.accounts.privileges import is_platform_administrator
from apps.core.audit import AdminAction, record_admin_action

# 32 bytes of entropy, URL-safe. Long enough that guessing is not a strategy —
# unlike login, a token endpoint has no account to lock out, so brute-force
# resistance has to come from the token itself.
VERIFICATION_TOKEN_BYTES = 32

# Long enough to survive a spam folder and a night's sleep; short enough that a
# link forwarded months later is not still a working credential.
VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)


class InvalidRole(Exception):
    """A role that is not one of the three this system has."""


class RoleUnchanged(Exception):
    """The requested role is the one already held.

    Refused rather than ignored: writing an audit row for a change that did not
    happen fills the trail with non-events, and a trail nobody reads is not a
    control.
    """


class NotPermitted(Exception):
    """The actor may not take this action.

    **Checked here rather than in a view, which diverges from `change_role` on
    purpose.** `change_role` takes an actor and audits it but leaves
    authorisation to Django Admin, because that is its only caller. Invitations
    will be issued from a command, a test and later an endpoint, and "only an
    administrator may admit people to the beta" is a rule about the operation,
    not about one transport (invariant 2). A view-level check would be absent
    from every other caller.
    """


class InvitationNotFound(Exception):
    """No invitation exists for this address.

    Distinct from expired and revoked so callers can log precisely. **Callers
    facing the public must still answer identically in all three cases** — the
    same account-enumeration argument that governs `EmailAlreadyRegistered`
    applies to admission, and knowing an address is invited is knowing somebody
    signed it up.
    """


class InvitationNotUsable(Exception):
    """The invitation exists but cannot be consumed: expired, revoked or spent."""


class NotTransactional(Exception):
    """Consumption was attempted outside a transaction.

    Spending an invitation only means something as part of creating an account.
    Called bare, the `UPDATE` autocommits, and a caller that then fails has spent
    an admission for nobody — a state no test would catch, because the invitation
    looks correctly consumed.

    A guard rather than a docstring because the mistake is a *caller's*, and the
    caller that will make it does not exist yet (slice 3a).
    """


class InvitationIssueConflict(Exception):
    """Another administrator issued to this address at the same moment.

    The insert lost a race on the unique constraint. Raised instead of letting the
    `IntegrityError` escape, which would be a 500 naming the constraint that
    failed — the same reasoning as `EmailAlreadyRegistered`, which exists in this
    module for exactly that.
    """


class InvitationAlreadyConsumed(Exception):
    """Re-issuing to an address that already registered.

    Refused rather than re-opened. A consumed invitation means an account
    exists, so re-admitting is at best meaningless and at worst a way to hand a
    second admission to somebody whose first was deliberate. Account deletion is
    not built (ADR-036 §5), so there is no case where this is the right move
    today; if one appears, it needs a decision rather than a quiet reset.
    """


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


@transaction.atomic
def register_account(*, email: str, password: str) -> User:
    """Create an account, applying the beta admission policy.

    **The policy lives here rather than in the view** (invariant 2) and rather
    than in `create_account`. Putting it in `create_account` was the obvious move
    and would have been wrong twice over: that function is called by management
    commands, the Django admin and most of the backend test suite, so an
    unconditional invitation requirement there would have broken several hundred
    tests and locked operators out of creating the very first accounts.

    So `create_account` keeps its contract — *make a user and a profile* — and
    this composes it with admission, which is a separate question.

    **Atomic, and that is what `consume_invitation`'s transaction guard was for.**
    The account is created first, because consumption needs a `User` to record as
    `consumed_by`; a refusal then rolls the account back. Slice 2 added
    `NotTransactional` to make sure a caller could not spend an admission outside
    a transaction and leave it spent for nobody — this is the caller it was
    guarding against, and the guard now has a real one.

    **`BETA_INVITATION_REQUIRED` gates the public endpoint, not the system.** With
    it on, `manage.py` and the admin can still create accounts. That is deliberate
    and necessary: somebody has to be able to admit the first cohort.

    Raises `EmailAlreadyRegistered` or, when admission is required and refused,
    whatever `consume_invitation` raises — `InvitationNotFound` for an address
    never invited and `InvitationNotUsable` for one expired, revoked or already
    spent. **Callers facing the public must not distinguish them**, for the same
    account-enumeration reason `EmailAlreadyRegistered` is answered silently
    (§7.1): which of the three it is tells somebody whether an address is on the
    invitation list.
    """
    user = create_account(email=email, password=password)

    if settings.BETA_INVITATION_REQUIRED:
        consume_invitation(user=user, request=None)

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


class InvalidPasswordResetToken(Exception):
    """Unknown, expired, or already consumed — one exception for all three."""


class IncorrectPassword(Exception):
    """The current password supplied to a change did not match."""


# Deliberately far shorter than verification's 24 hours. A leaked verification
# token marks an address confirmed; a leaked reset token is account takeover.
PASSWORD_RESET_TOKEN_LIFETIME = timedelta(hours=1)


def issue_password_reset(*, user: User) -> str:
    """Create a reset token and return the raw value, which is never stored."""
    raw = secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)

    PasswordResetToken.objects.create(
        user=user,
        token_hash=_hash_token(raw),
        expires_at=timezone.now() + PASSWORD_RESET_TOKEN_LIFETIME,
    )

    return raw


@transaction.atomic
def reset_password(*, token: str, new_password: str) -> User:
    """Consume a token and set a new password.

    Changing the password rotates Django's session auth hash, which invalidates
    every existing session for the account. That is the point rather than a
    side effect: someone resetting their password may be doing it *because*
    they think an attacker has access, and leaving the attacker's session alive
    would defeat the whole exercise.

    Locked read, so two requests racing the same emailed link cannot both
    succeed.
    """
    if not token:
        raise InvalidPasswordResetToken

    try:
        record = PasswordResetToken.objects.select_for_update().get(token_hash=_hash_token(token))
    except PasswordResetToken.DoesNotExist as exc:
        raise InvalidPasswordResetToken from exc

    if record.consumed_at is not None:
        raise InvalidPasswordResetToken
    if record.expires_at <= timezone.now():
        raise InvalidPasswordResetToken

    record.consumed_at = timezone.now()
    record.save(update_fields=["consumed_at", "updated_at"])

    user = record.user
    user.set_password(new_password)
    user.save(update_fields=["password"])

    # Any other reset token outstanding for this account is now moot, and
    # leaving them live would mean an attacker who requested one earlier still
    # holds a working key.
    PasswordResetToken.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )

    return user


def change_password(*, user: User, current_password: str, new_password: str) -> User:
    """Change a signed-in user's password.

    The current password is required even though the caller is authenticated.
    A session left open on a shared machine is exactly the situation this
    stops, and it is cheap insurance against a stolen session becoming a
    permanent one.
    """
    if not user.check_password(current_password):
        raise IncorrectPassword

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return user


@transaction.atomic
def change_role(*, actor: User, user: User, role: str, reason: str, request=None) -> User:
    """Move somebody between student, instructor and administrator.

    §6.10 calls this "instructor approval" and puts it in Django Admin. It is
    an administrative action in §8's list, so it writes an audit row naming who
    changed what, from what, to what, and why.

    **Refuses a no-op.** Saving the change form without touching the role would
    otherwise write an audit row saying a role changed when it did not, and a
    trail full of non-events is one nobody reads.

    Does not touch `is_staff`. That is the Django admin's own gate and a wider
    capability than any role — accounts.models draws the distinction, and
    granting it through a role dropdown would erase it.
    """
    if role not in Role.values:
        raise InvalidRole(role)

    previous = user.role
    if previous == role:
        raise RoleUnchanged(role)

    user.role = role
    user.save(update_fields=["role"])

    record_admin_action(
        actor=actor,
        action=AdminAction.ROLE_CHANGED,
        target=user,
        reason=reason,
        request=request,
        previous_role=previous,
        new_role=role,
    )
    return user


# How long an admission stays open. Long enough that an invitation sent on a
# Friday survives a holiday; short enough that a beta cohort does not quietly
# stay admissible for a year. Not a security boundary — email verification is
# still the proof of inbox ownership — so this is an operational choice.
INVITATION_LIFETIME = timedelta(days=30)


def _invitations_for(email: str):
    """Rows for this address, matched the way the unique constraint matches.

    **The lookups used to be `email__iexact`, which does not agree with the
    constraint.** Django compiles `__iexact` to `UPPER("email"::text) = UPPER(%s)`
    — checked by printing the SQL, not recalled — while
    `UniqueConstraint(Lower("email"))` is a functional index on `lower(email)`.

    Two consequences. The certain one is that **no index could serve any
    invitation lookup**: a `lower(email)` index cannot answer an `UPPER(...)`
    predicate, so all five were sequential scans. The second is that uniqueness
    and lookup were deciding "same address" with different functions, and
    `UPPER`/`LOWER` are not inverses for every character — so in principle the
    constraint could permit two rows that a lookup matched as one, and
    `.update()` would then consume both before the `spent != 1` check noticed.

    Honest about the scale: I could not demonstrate a colliding pair in this
    Postgres — `upper('straße')` is `'STRAẞE'`, not `'STRASSE'`, so the obvious
    candidate does not collide. This is a latent inconsistency between two
    functions rather than a reproduced data bug. It is fixed because matching the
    constraint costs nothing and reasoning about when it bites costs more.
    """
    return BetaInvitation.objects.alias(_key=Lower("email")).filter(_key=email.strip().lower())


def _require_admin(actor: User) -> None:
    """Only an active administrator may admit or exclude people.

    **Defers to `privileges.is_platform_administrator` rather than asking again.**
    The first version tested `actor.role != Role.ADMIN` inline, which was an
    eighth copy of a predicate that module exists to hold — it opens "Two
    predicates, in one place, because they were in seven" and records that the
    definition had already drifted once. Writing a ninth would be the same
    mistake with a fresh docstring.

    That copy also omitted `is_superuser`, and the consequence was an operational
    dead end rather than extra safety. `create_superuser` does not set `role`, so
    a bootstrap account from `manage.py createsuperuser` has `role=STUDENT`: it
    could grant paid access overrides and read billing history, but could not
    issue a single beta invitation — and it cannot promote itself, because
    `UserAdmin` makes `role` read-only on one's own account and registration is
    itself invitation-gated. The only route to the first admission would have
    been `manage.py shell`. Widened to match the rest of the codebase on the
    owner's decision of 2026-10-31.

    **`is_active` is composed on top, and is not a disagreement with that
    module.** The two answer different questions: `is_platform_administrator` is
    *who administers content they do not own*, `is_active` is *whether this
    account may act at all*. A deactivated administrator is somebody whose access
    was taken away, and an operation that still honoured them would make
    deactivation decorative.
    """
    if actor is None or not getattr(actor, "pk", None):
        raise NotPermitted("An invitation action must name who took it.")
    if not actor.is_active or not is_platform_administrator(actor):
        raise NotPermitted(f"{actor.email} is not an active administrator.")


@transaction.atomic
def issue_invitation(*, actor: User, email: str, reason: str, request=None) -> BetaInvitation:
    """Admit an email address to the private beta.

    **Re-opens an existing row rather than inserting a second one.** The unique
    constraint on `Lower(email)` makes an address admissible exactly once, so a
    revoked invitation has to be resurrected or it is a dead end: revoke
    somebody and they could never be re-admitted. That is the shape the owner
    chose on 2026-10-30, and the row's history lives in the audit log.

    Refuses to re-open a *consumed* invitation — see `InvitationAlreadyConsumed`.

    Issuing has no effect on registration or on `resolve_access`. This record is
    admission, not entitlement (invariant 3), and nothing reads it until slice
    3a wires it into signup.
    """
    _require_admin(actor)

    normalised = email.strip()
    if not normalised:
        raise InvitationNotFound("An invitation needs an email address.")

    now = timezone.now()
    expires_at = now + INVITATION_LIFETIME

    # `Lower("email")` is what the constraint indexes, so the lookup has to match
    # it or a re-issue inserts a duplicate and dies on the constraint instead.
    # `select_for_update`, because the re-open decision below is a check-then-act.
    # Without the lock an administrator re-issuing while somebody registers could
    # read "not consumed", and then clear `revoked_at` and extend `expires_at` on a
    # row that was consumed in between — auditing it as `reopened` and silently
    # undoing the refusal `InvitationAlreadyConsumed` exists to make.
    existing = _invitations_for(normalised).select_for_update().first()

    if existing is None:
        try:
            # Savepointed, so a lost race does not poison the outer transaction.
            with transaction.atomic():
                invitation = BetaInvitation.objects.create(email=normalised, expires_at=expires_at)
        except IntegrityError as error:
            # Two administrators issuing to the same new address: both read
            # nothing, both insert, one loses. A raw IntegrityError escaping here
            # is a 500 that names the constraint — the failure
            # `EmailAlreadyRegistered` exists a few hundred lines up to prevent.
            # Surfaced as something a caller can act on; retrying is the caller's
            # choice, because re-opening a row somebody else just created is a
            # different operation from the one that was asked for.
            raise InvitationIssueConflict(normalised) from error
        reopened = False
    else:
        if existing.consumed_at is not None:
            raise InvitationAlreadyConsumed(normalised)
        existing.email = normalised
        existing.expires_at = expires_at
        existing.revoked_at = None
        existing.save(update_fields=["email", "expires_at", "revoked_at", "updated_at"])
        invitation = existing
        reopened = True

    record_admin_action(
        actor=actor,
        action=AdminAction.BETA_INVITATION_ISSUED,
        target=invitation,
        reason=reason,
        request=request,
        invited_email=normalised,
        expires_at=expires_at.isoformat(),
        reopened=reopened,
    )
    return invitation


@transaction.atomic
def revoke_invitation(*, actor: User, email: str, reason: str, request=None) -> BetaInvitation:
    """Withdraw an admission that has not been used.

    A consumed invitation is not revocable: the account already exists, and
    pretending otherwise would suggest revoking here removes access. Taking
    access away from an existing account is a different operation
    (`change_role`, or the deletion ADR-036 §5 has not decided).

    Idempotent on an already-revoked invitation — re-revoking writes no second
    audit row, for the same reason `change_role` refuses a no-op: a trail full
    of non-events is one nobody reads.
    """
    _require_admin(actor)

    # Locked for the same check-then-act reason as issuing: without it a revoke
    # racing a consume commits `revoked_at` onto an already-consumed row, a
    # consumed-and-revoked state no constraint forbids, plus an audit row saying
    # an admission was withdrawn that had in fact already been used.
    invitation = _invitations_for(email).select_for_update().first()
    if invitation is None:
        raise InvitationNotFound(email)
    if invitation.consumed_at is not None:
        raise InvitationAlreadyConsumed(email)
    if invitation.revoked_at is not None:
        return invitation

    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at", "updated_at"])

    record_admin_action(
        actor=actor,
        action=AdminAction.BETA_INVITATION_REVOKED,
        target=invitation,
        reason=reason,
        request=request,
        invited_email=invitation.email,
    )
    return invitation


def consume_invitation(*, user: User, request=None) -> BetaInvitation:
    """Spend an admission, exactly once, for the account it produced.

    **The address comes from the account, and cannot be passed separately.**

    The first version took `email` and `user` as independent arguments, and
    nothing required them to agree. Slice 3a is where a real caller appears, and
    a caller that paired the wrong two would consume one person's admission to
    create another person's account — a hole no test here would have caught,
    because every test passed a matching pair.

    Validating that they match was the alternative. Deriving the address from
    `user.email` is stronger: there is no second value to get wrong, so the bad
    state is unrepresentable rather than merely detected. That is invariant 11's
    argument applied to a function signature instead of a column.

    **Must be called inside the caller's transaction, and refuses otherwise.**

    The guarantee slice 2 owes is that a failed account creation leaves the
    invitation unspent, and that guarantee comes entirely from the *caller's*
    transaction — `create_account` is already atomic, so a rollback there undoes
    this too.

    An earlier version of this docstring claimed the function was "deliberately
    not decorated `@transaction.atomic`" because a nested block could commit the
    consumption while the outer transaction rolled back. **That was wrong, and
    provoking it is what showed so**: adding the decorator changes nothing,
    because Django's nested `atomic` is a savepoint and an outer rollback discards
    it. Undecorated and decorated behave identically here, inside a transaction
    and out of one.

    What actually threatened the guarantee was that *nothing required a caller to
    have a transaction at all*. Called bare, the `UPDATE` autocommits, and a
    caller that then fails to create the account has spent an invitation for
    nobody. Slice 3a is where that mistake would be made. So the requirement is
    now checked rather than described — the decorator would have hidden it by
    silently supplying a transaction of this function's own.

    **Single-use is enforced by a conditional UPDATE, not by a read.** The
    `WHERE consumed_at IS NULL` is evaluated by the database while it holds the
    row, so two concurrent registrations cannot both see an unconsumed row and
    both write. A `filter().first()` followed by `save()` would let exactly that
    happen, and the window is small enough to pass every sequential test.
    Double-consumption is a *transition*, not a state, so it cannot be a
    `CheckConstraint`; this is the closest the database gets.
    """
    if not transaction.get_connection().in_atomic_block:
        raise NotTransactional(
            "consume_invitation must run inside the caller's transaction, "
            "so a failed account creation leaves the invitation unspent."
        )

    normalised = (user.email or "").strip()
    if not normalised:
        raise InvitationNotFound("The account has no email address to admit.")

    now = timezone.now()

    spent = (
        _invitations_for(normalised)
        .filter(
            consumed_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        .update(consumed_at=now, consumed_by=user, updated_at=now)
    )

    if spent != 1:
        # One query to say *why*, and only on the failure path. The reason never
        # reaches a public response — §7.1 account enumeration applies to
        # admission too — but an operator reading logs needs to tell "never
        # invited" from "invited and let it lapse".
        invitation = _invitations_for(normalised).first()
        if invitation is None:
            raise InvitationNotFound(normalised)
        raise InvitationNotUsable(normalised)

    invitation = _invitations_for(normalised).get()

    record_admin_action(
        actor=user,
        action=AdminAction.BETA_INVITATION_CONSUMED,
        target=invitation,
        reason="Account created against a beta invitation.",
        request=request,
        invited_email=invitation.email,
    )
    return invitation
