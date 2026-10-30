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
        assert "cohort one" in row.reason

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
        consume_invitation(email="guest@example.test", user=_learner("guest@example.test"))

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

        # Expired. Written directly rather than by waiting: the check constraint
        # requires expires_at > created_at, so an invitation cannot be *issued*
        # already expired — it has to lapse.
        issue_invitation(actor=admin, email="lapsed@example.test", reason="cohort one")
        BetaInvitation.objects.filter(email="lapsed@example.test").update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        with pytest.raises(InvitationNotUsable):
            consume_invitation(email="lapsed@example.test", user=_learner("a@example.test"))

        # Revoked.
        issue_invitation(actor=admin, email="gone@example.test", reason="cohort one")
        revoke_invitation(actor=admin, email="gone@example.test", reason="changed my mind")
        with pytest.raises(InvitationNotUsable):
            consume_invitation(email="gone@example.test", user=_learner("b@example.test"))

        # Never invited — a distinct exception so operators can tell these apart
        # in logs, even though a public response must not.
        with pytest.raises(InvitationNotFound):
            consume_invitation(email="stranger@example.test", user=_learner("c@example.test"))

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

        first = _learner("first@example.test")
        consume_invitation(email="guest@example.test", user=first)

        with pytest.raises(InvitationNotUsable):
            consume_invitation(email="guest@example.test", user=_learner("second@example.test"))

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        # Still the first account. A second consume must not re-point the record.
        assert invitation.consumed_by_id == first.pk
        assert _audit_count("BETA_INVITATION_CONSUMED") == 1

    def test_consumption_links_the_account_it_produced(self) -> None:
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import consume_invitation, issue_invitation

        admin = _admin()
        issue_invitation(actor=admin, email="guest@example.test", reason="cohort one")
        user = _learner("guest@example.test")

        consume_invitation(email="guest@example.test", user=user)

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
            consume_invitation(email="guest@example.test", user=user)
            raise AccountCreationFailed

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        assert invitation.consumed_at is None
        assert invitation.consumed_by is None
        assert _audit_count("BETA_INVITATION_CONSUMED") == 0

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
        racers = [_learner("one@example.test"), _learner("two@example.test")]

        start = threading.Barrier(len(racers))
        outcomes: list[str] = []
        lock = threading.Lock()

        def attempt(user) -> None:
            try:
                start.wait(timeout=10)
                with transaction.atomic():
                    consume_invitation(email="guest@example.test", user=user)
                result = "consumed"
            except InvitationNotUsable:
                result = "refused"
            except Exception as error:
                result = f"error: {type(error).__name__}: {error}"
            finally:
                # Each thread gets its own connection; leaking them exhausts the
                # test database's pool across a run.
                connection.close()
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=attempt, args=(user,)) for user in racers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(outcomes) == ["consumed", "refused"], outcomes
        assert BetaInvitation.objects.filter(consumed_at__isnull=False).count() == 1
        assert _audit_count("BETA_INVITATION_CONSUMED") == 1
