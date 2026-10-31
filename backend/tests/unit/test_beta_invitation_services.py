"""Invitation services: who may admit, and spending an admission exactly once.

Slice 2 of the private-beta plan. Two things have to be true and neither is
provable by reading the code:

1. **Only an active administrator may admit or exclude.** The authorisation check
   lives in the service rather than a view, which diverges from `change_role` on
   purpose — invitations are issued from commands and tests as well as endpoints,
   so a view-level check would be absent from most callers.
2. **An invitation is spent at most once, and never by a registration that
   failed.** Both are transactional claims, so both are tested against a real
   database with real transactions. The plan is explicit that mocks asserting a
   service was called prove nothing, and CLAUDE.md §6 forbids them.

Nothing here touches registration. Wiring admission into signup is slice 3a,
which the plan gates behind its own approval.
"""

import threading
import time
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _admin(email: str = "admin@example.test"):
    from apps.accounts.models import Role
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


def _learner(email: str = "learner@example.test"):
    from apps.accounts.services import create_account

    return create_account(email=email, password=PASSWORD)


def _audit_count(action: str) -> int:
    from apps.core.models import AuditLog

    return AuditLog.objects.filter(action=action).count()


class TestWhoMayAdmit:
    def test_non_admin_cannot_issue_invitation(self) -> None:
        """A student and an instructor are both refused, and nothing is written.

        The second assertion is the one that matters: a service that raised
        *after* inserting would leave an admission behind that nobody authorised.
        """
        from apps.accounts.models import BetaInvitation, Role
        from apps.accounts.services import NotPermitted, issue_invitation

        student = _learner("student@example.test")
        instructor = _learner("instructor@example.test")
        instructor.role = Role.INSTRUCTOR
        instructor.save(update_fields=["role"])

        for actor in (student, instructor):
            with pytest.raises(NotPermitted):
                issue_invitation(actor=actor, email="guest@example.test", reason="why not")

        assert BetaInvitation.objects.count() == 0
        assert _audit_count("BETA_INVITATION_ISSUED") == 0

    def test_a_bootstrap_superuser_can_issue(self) -> None:
        """The reason the predicate was widened on 2026-10-31.

        `create_superuser` does not touch `role`, so a `manage.py createsuperuser`
        account has `role=STUDENT`. Before this, it could grant paid access
        overrides and read billing history but could not issue one beta
        invitation — and it cannot promote itself, because `UserAdmin` makes
        `role` read-only on one's own account and registration is itself
        invitation-gated. The only route to the first admission was
        `manage.py shell`.

        This is the bootstrap case `privileges.is_platform_administrator`
        documents as "the kind of sharp edge nobody finds until the first
        production incident", and deferring to that predicate is what fixed it.
        """
        from apps.accounts.models import BetaInvitation, Role, User
        from apps.accounts.services import issue_invitation

        root = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
        # The precondition that made this a dead end: superuser, no admin role.
        assert root.is_superuser is True
        assert root.role == Role.STUDENT

        issue_invitation(actor=root, email="first-tester@example.test", reason="cohort one")

        assert BetaInvitation.objects.filter(email="first-tester@example.test").exists()

    def test_a_deactivated_administrator_cannot_issue(self) -> None:
        # Deactivation is how access is taken away. An operation that still
        # honoured the role would make it decorative.
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import NotPermitted, issue_invitation

        actor = _admin()
        actor.is_active = False
        actor.save(update_fields=["is_active"])

        with pytest.raises(NotPermitted):
            issue_invitation(actor=actor, email="guest@example.test", reason="why not")

        assert BetaInvitation.objects.count() == 0

    def test_non_admin_cannot_revoke(self) -> None:
        from apps.accounts.services import NotPermitted, issue_invitation, revoke_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")

        with pytest.raises(NotPermitted):
            revoke_invitation(
                actor=_learner(), email="guest@example.test", reason="not mine to take"
            )


class TestIssuing:
    def test_issuing_records_who_and_why(self) -> None:
        from apps.accounts.services import issue_invitation
        from apps.core.models import AuditLog

        admin = _admin()
        invitation = issue_invitation(actor=admin, email="Guest@Example.test", reason="cohort one")

        assert invitation.expires_at > timezone.now()
        assert invitation.consumed_at is None
        assert invitation.consumed_by is None

        row = AuditLog.objects.get(action="BETA_INVITATION_ISSUED")
        assert row.actor_label == admin.email
        assert row.target_id == str(invitation.pk)
        # `reason` is not a column — `record_admin_action` puts it in `metadata`
        # beside the extra details. Asserted against the real shape, because the
        # first version of this test read `row.reason` and passed nothing.
        assert row.metadata["reason"] == "cohort one"
        assert row.metadata["invited_email"] == "Guest@Example.test"
        assert row.metadata["reopened"] is False

    def test_revoked_invitation_can_be_reissued(self) -> None:
        """The owner's decision of 2026-10-30, and the reason it was needed.

        `UniqueConstraint(Lower("email"))` is unconditional, so a second row for
        the same address is impossible. Without re-opening, revoking somebody
        would permanently exclude them — a dead end reachable by one ordinary
        operator action.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import issue_invitation, revoke_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        revoke_invitation(actor=admin, email="guest@example.test", reason="left the company")

        reissued = issue_invitation(actor=admin, email="guest@example.test", reason="rejoined")

        assert reissued.revoked_at is None
        assert reissued.expires_at > timezone.now()
        # Re-opened, not duplicated.
        assert BetaInvitation.objects.count() == 1
        assert _audit_count("BETA_INVITATION_ISSUED") == 2

    def test_consumed_invitation_cannot_be_reissued(self) -> None:
        # A consumed invitation means an account exists. Re-opening would hand a
        # second admission to somebody whose first was deliberate, and account
        # deletion is not built (ADR-036 §5), so there is no legitimate case.
        from apps.accounts.services import (
            InvitationAlreadyConsumed,
            consume_invitation,
            issue_invitation,
        )

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        consume_invitation(user=_learner("guest@example.test"))

        with pytest.raises(InvitationAlreadyConsumed):
            issue_invitation(actor=admin, email="guest@example.test", reason="again")

    def test_a_failed_issue_leaves_no_audit_row(self) -> None:
        """Audit rollback, which the plan asks for by name.

        `issue_invitation` is atomic, so a failure after the insert must take the
        audit row with it. Forced by a `reason` the audit layer refuses — the
        realistic version of this, since `record_admin_action` validates last.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import issue_invitation
        from apps.core.audit import NotAuditable

        admin = _admin()

        with pytest.raises(NotAuditable):
            issue_invitation(actor=admin, email="guest@example.test", reason="   ")

        assert BetaInvitation.objects.count() == 0
        assert _audit_count("BETA_INVITATION_ISSUED") == 0


class TestIdentityAndIntegrity:
    def test_lookups_match_the_constraint_on_case(self) -> None:
        """Issued in one casing, found in another, by every service.

        The lookups used `email__iexact`, which Django compiles to
        `UPPER("email"::text) = UPPER(%s)`, while the unique constraint is a
        functional index on `lower(email)`. They now use the same function the
        constraint uses, so "same address" has one definition.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import issue_invitation, revoke_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="MixedCase@Example.test", reason="cohort one")

        revoke_invitation(
            actor=admin, email="  mixedcase@EXAMPLE.TEST  ", reason="found by any casing"
        )

        invitation = BetaInvitation.objects.get()
        assert invitation.revoked_at is not None

    def test_lookups_use_the_same_function_as_the_constraint(self) -> None:
        """Structural, because behaviour cannot tell the two apart here.

        The case test above passes against `email__iexact` too — both match
        case-insensitively, so it proves nothing about *which function* does the
        matching. Provoked and confirmed: reverting the helper to `__iexact` left
        all 18 tests green.

        What matters is that the lookup and `UniqueConstraint(Lower("email"))`
        agree. `__iexact` compiles to `UPPER("email"::text) = UPPER(%s)`, which a
        `lower(email)` index cannot serve and which decides "same address" by a
        different function than uniqueness does. So the SQL is asserted directly.
        """
        from apps.accounts.services import _invitations_for

        sql = str(_invitations_for("Guest@Example.test").query)

        assert "LOWER(" in sql.upper().replace("UPPER(", "")  # a LOWER call is present
        assert "UPPER(" not in sql, sql

    def test_no_service_lookup_uses_iexact(self) -> None:
        """The helper is only worth having if everything goes through it.

        Comments stripped first: the helper's own docstring explains why
        `email__iexact` is wrong, so grepping the raw source fails against correct
        code. That trap has now caught this repository eight times.
        """
        import re
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "apps" / "accounts" / "services.py"
        code = source.read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        code = re.sub(r"^\s*#.*$", "", code, flags=re.MULTILINE)

        assert "email__iexact" not in code

    def test_an_admitted_account_cannot_be_deleted(self) -> None:
        """`PROTECT`, because `SET_NULL` could never have executed.

        `SET_NULL` produces `consumed_at` set with `consumed_by` null, which is
        exactly what `beta_invitation_consumption_is_complete` forbids — so the
        delete would have failed with an IntegrityError naming a constraint rather
        than preserving history as its comment claimed. `PROTECT` puts the
        contradiction at the point of decision: account deletion is not built
        (ADR-036 §5), and when it is, it has to cover admission records.
        """
        from django.db.models import ProtectedError

        from apps.accounts.services import consume_invitation, issue_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        user = _learner("guest@example.test")
        with transaction.atomic():
            consume_invitation(user=user)

        with pytest.raises(ProtectedError):
            user.delete()

    @pytest.mark.django_db(transaction=True)
    def test_revoking_while_a_consume_is_in_flight_is_refused(self) -> None:
        """The check-then-act the lock closes.

        `revoke_invitation` reads the row, decides it is not consumed, then writes
        `revoked_at`. Unlocked, an administrator revoking while somebody registers
        reads the pre-commit state, finds the invitation unconsumed, and stamps
        `revoked_at` onto a row that was consumed in between — a consumed *and*
        revoked state no constraint forbids, plus an audit row claiming an
        admission was withdrawn that had in fact already been used.

        Sequenced, not raced: the consume holds its transaction open until the
        revoke is underway, so the revoke's `SELECT ... FOR UPDATE` genuinely has
        to wait on the row and re-read it after the commit.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            InvitationAlreadyConsumed,
            consume_invitation,
            issue_invitation,
            revoke_invitation,
        )

        admin = _admin()
        with transaction.atomic():
            issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        user = _learner("guest@example.test")

        consumed = threading.Event()
        revoke_running = threading.Event()
        outcomes: dict[str, str] = {}

        def consuming() -> None:
            try:
                with transaction.atomic():
                    consume_invitation(user=user)
                    consumed.set()
                    revoke_running.wait(timeout=15)
                    time.sleep(0.5)
                outcomes["consume"] = "consumed"
            except Exception as error:
                outcomes["consume"] = f"error: {type(error).__name__}: {error}"
            finally:
                connection.close()

        def revoking() -> None:
            try:
                consumed.wait(timeout=15)
                revoke_running.set()
                revoke_invitation(actor=admin, email="guest@example.test", reason="too late")
                outcomes["revoke"] = "revoked"
            except InvitationAlreadyConsumed:
                outcomes["revoke"] = "refused"
            except Exception as error:
                outcomes["revoke"] = f"error: {type(error).__name__}: {error}"
            finally:
                connection.close()

        threads = [threading.Thread(target=consuming), threading.Thread(target=revoking)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert outcomes == {"consume": "consumed", "revoke": "refused"}, outcomes

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        # The state the lock exists to prevent: used and withdrawn at once.
        assert invitation.consumed_at is not None
        assert invitation.revoked_at is None
        assert _audit_count("BETA_INVITATION_REVOKED") == 0

    @pytest.mark.django_db(transaction=True)
    def test_a_lost_insert_race_is_a_handleable_conflict(self) -> None:
        """Two administrators issuing to the same new address.

        Neither can lock a row that does not exist yet, so both read nothing and
        both insert. The loser used to get a raw `IntegrityError` out of the
        service — a 500 naming the constraint, the failure
        `EmailAlreadyRegistered` exists in this module to prevent.

        Sequenced rather than raced: the other administrator's insert is held
        uncommitted, so our read genuinely sees nothing and our insert blocks on
        the unique index until they commit.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import InvitationIssueConflict, issue_invitation

        admin = _admin()
        inserted = threading.Event()
        may_commit = threading.Event()

        def other_administrator() -> None:
            try:
                with transaction.atomic():
                    BetaInvitation.objects.create(
                        email="contested@example.test",
                        expires_at=timezone.now() + timedelta(days=1),
                    )
                    inserted.set()
                    may_commit.wait(timeout=15)
            finally:
                connection.close()

        def release_once_we_are_blocked() -> None:
            # Our insert is blocked on the index by the time this fires; letting the
            # other transaction commit is what turns that block into a violation.
            time.sleep(0.5)
            may_commit.set()

        other = threading.Thread(target=other_administrator)
        other.start()
        assert inserted.wait(timeout=15)
        threading.Thread(target=release_once_we_are_blocked).start()

        with pytest.raises(InvitationIssueConflict):
            issue_invitation(actor=admin, email="contested@example.test", reason="race")

        other.join(timeout=15)
        assert BetaInvitation.objects.filter(email="contested@example.test").count() == 1


class TestConsumption:
    def test_expired_or_revoked_invitation_is_refused(self) -> None:
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            InvitationNotFound,
            InvitationNotUsable,
            consume_invitation,
            issue_invitation,
            revoke_invitation,
        )

        admin = _admin()

        # Expired. **Both timestamps move**, which is the point: the check
        # constraint requires `expires_at > created_at`, so an invitation cannot
        # be issued already expired — it has to *lapse*. Pushing only
        # `expires_at` into the past violates the constraint, which is how the
        # first version of this test failed. So this simulates an invitation
        # issued long ago whose window has closed, and the constraint stays
        # satisfied throughout.
        issue_invitation(actor=admin, email="lapsed@example.test", reason="cohort one")
        issued = timezone.now() - timedelta(days=40)
        BetaInvitation.objects.filter(email="lapsed@example.test").update(
            created_at=issued, expires_at=issued + timedelta(days=30)
        )
        with pytest.raises(InvitationNotUsable):
            consume_invitation(user=_learner("lapsed@example.test"))

        # Revoked.
        issue_invitation(actor=admin, email="gone@example.test", reason="cohort one")
        revoke_invitation(actor=admin, email="gone@example.test", reason="changed my mind")
        with pytest.raises(InvitationNotUsable):
            consume_invitation(user=_learner("gone@example.test"))

        # Never invited — a distinct exception so operators can tell these apart
        # in logs, even though a public response must not.
        with pytest.raises(InvitationNotFound):
            consume_invitation(user=_learner("stranger@example.test"))

        assert _audit_count("BETA_INVITATION_CONSUMED") == 0

    def test_invitation_cannot_be_consumed_twice(self) -> None:
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            InvitationNotUsable,
            consume_invitation,
            issue_invitation,
        )

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")

        # **The same account twice, because a different one can no longer reach this
        # invitation at all.** Since slice 2 derives the address from `user.email`,
        # and an account's email is unique, only the invited account can consume its
        # own invitation — the "somebody else spends my admission" case is now
        # unrepresentable rather than merely refused. What remains to prove is that
        # the invited account cannot spend it twice.
        first = _learner("guest@example.test")
        consume_invitation(user=first)

        with pytest.raises(InvitationNotUsable):
            consume_invitation(user=first)

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        # Still the first consumption. A second attempt must not re-stamp the record.
        assert invitation.consumed_by_id == first.pk
        assert _audit_count("BETA_INVITATION_CONSUMED") == 1

    def test_consumption_links_the_account_it_produced(self) -> None:
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import consume_invitation, issue_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        user = _learner("guest@example.test")

        consume_invitation(user=user)

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        assert invitation.consumed_at is not None
        assert invitation.consumed_by_id == user.pk

    def test_half_consumed_rows_are_refused_by_the_database(self) -> None:
        """Invariant 11: consumption is one fact in two columns.

        A row with `consumed_at` and no `consumed_by` reads as "somebody used
        this and we do not know who", which is a bug wearing the clothes of a
        state. Asserted against the constraint, not the service, because direct
        and bulk writes bypass Python.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import issue_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")

        with pytest.raises(IntegrityError), transaction.atomic():
            BetaInvitation.objects.filter(email="guest@example.test").update(
                consumed_at=timezone.now()
            )


class TestTransactionalGuarantees:
    def test_account_failure_does_not_consume_invitation(self) -> None:
        """The guarantee slice 2 exists to provide.

        `consume_invitation` is deliberately **not** decorated
        `@transaction.atomic`: a nested atomic block would create a savepoint that
        could commit the consumption while the outer transaction rolled the
        account back. Joining the caller's transaction is what makes a rollback
        undo it, and this is the test that would catch the decorator being added
        "for safety".
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import consume_invitation, issue_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")

        class AccountCreationFailed(Exception):
            pass

        user = _learner("guest@example.test")

        with pytest.raises(AccountCreationFailed), transaction.atomic():
            consume_invitation(user=user)
            raise AccountCreationFailed

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        assert invitation.consumed_at is None
        assert invitation.consumed_by is None
        assert _audit_count("BETA_INVITATION_CONSUMED") == 0

    @pytest.mark.django_db(transaction=True)
    def test_consuming_outside_a_transaction_is_refused(self) -> None:
        """The guarantee is the caller's transaction, so the caller must have one.

        `transaction=True` turns autocommit back on, which is the state a bare
        caller would be in. Without the guard the UPDATE commits on its own and a
        caller that then fails has spent an admission for nobody — a state no
        other test here catches, because the invitation looks correctly consumed.

        This replaced a docstring claim that was simply false: that omitting
        `@transaction.atomic` was what protected the rollback. Provoking it showed
        the decorator changes nothing, since Django's nested atomic is a savepoint
        an outer rollback discards. The real hole was that nothing required a
        caller to have a transaction at all.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            NotTransactional,
            consume_invitation,
            issue_invitation,
        )

        admin = _admin()
        with transaction.atomic():
            issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        user = _learner("guest@example.test")

        with pytest.raises(NotTransactional):
            consume_invitation(user=user)

        assert BetaInvitation.objects.get(email="guest@example.test").consumed_at is None

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_consumption_admits_exactly_one(self) -> None:
        """Two real transactions racing for one invitation.

        The sequential double-consume test above passes against a
        `filter().first()` followed by `save()`, because nothing interleaves. This
        one does not: both threads open a transaction, both target the same row,
        and only the conditional `UPDATE ... WHERE consumed_at IS NULL` makes the
        database decide. That is why single-use is a conditional update rather
        than a read-then-write.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            InvitationNotUsable,
            consume_invitation,
            issue_invitation,
        )

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        # One account, two concurrent attempts — two registrations of the same email
        # arriving together, which is the real race now that the address comes from
        # the account rather than an argument.
        racer = _learner("guest@example.test")

        # **Sequenced, not merely started together.** The first version used a
        # `threading.Barrier`, which aligns when the threads *start* — but each then
        # opens its first database connection, and that cost dominates and varies
        # enough that one attempt routinely finishes before the other reads. Measured,
        # not guessed: against a read-then-write implementation the barrier version
        # passed, because the two never overlapped. It had caught the bug once by
        # luck, which is worse than not having it.
        #
        # So the overlap is forced. The first attempt holds its transaction open until
        # the second is underway; the second therefore issues its UPDATE while the
        # first still holds the row lock. Correct code makes the second re-evaluate
        # `consumed_at IS NULL` after the commit and find nothing. A read-then-write
        # reads the pre-commit state, decides the row is free, and overwrites.
        first_consumed = threading.Event()
        second_running = threading.Event()
        outcomes: dict[str, str] = {}

        def first_attempt() -> None:
            try:
                with transaction.atomic():
                    consume_invitation(user=racer)
                    first_consumed.set()
                    second_running.wait(timeout=15)
                    # The second attempt has entered its transaction; give it long
                    # enough to reach the UPDATE and block on this row. A bounded
                    # sleep is the standard shape for a lock-ordering test — there is
                    # no portable way to ask Postgres "is anybody waiting on me yet"
                    # without polling pg_locks from a third connection.
                    time.sleep(0.5)
                outcomes["first"] = "consumed"
            except InvitationNotUsable:
                outcomes["first"] = "refused"
            except Exception as error:
                outcomes["first"] = f"error: {type(error).__name__}: {error}"
            finally:
                # Each thread gets its own connection; leaking them exhausts the
                # test database's pool across a run.
                connection.close()

        def second_attempt() -> None:
            try:
                first_consumed.wait(timeout=15)
                second_running.set()
                with transaction.atomic():
                    consume_invitation(user=racer)
                outcomes["second"] = "consumed"
            except InvitationNotUsable:
                outcomes["second"] = "refused"
            except Exception as error:
                outcomes["second"] = f"error: {type(error).__name__}: {error}"
            finally:
                connection.close()

        threads = [
            threading.Thread(target=first_attempt),
            threading.Thread(target=second_attempt),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert outcomes == {"first": "consumed", "second": "refused"}, outcomes
        assert BetaInvitation.objects.filter(consumed_at__isnull=False).count() == 1
        assert _audit_count("BETA_INVITATION_CONSUMED") == 1
