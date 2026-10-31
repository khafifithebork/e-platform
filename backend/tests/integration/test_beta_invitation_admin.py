"""Admitting people to the beta through the admin, slice 3b-i.

The operator surface. Three things have to hold and none is visible from reading
the `ModelAdmin`:

1. **Issuing goes through the service**, so it is audited and names who did it.
   A `ModelAdmin` that saved the row itself would admit somebody with nothing
   recording who, which is the failure `UserAdmin.save_model` already avoids for
   role changes.
2. **A non-administrator cannot admit anybody**, even with admin-site access.
   Staff is the admin's own gate and a wider capability than any role
   (`accounts.models` draws that line), so holding it is not the same as being
   entitled to admit people.
3. **Nobody is created here.** The plan's acceptance for 3b says the operator
   flow must "never use Django Admin to create a passwordless user", and the
   admin already refuses — asserted below rather than assumed, because it is a
   property somebody could switch off in one line.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.audit import AdminAction
from apps.core.models import AuditLog
from tests.otp_helpers import verify_admin_session

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(
    email: str,
    *,
    role: str = Role.STUDENT,
    staff: bool = False,
    superuser: bool = False,
):
    """Build an account. `staff` and `superuser` are **separate on purpose**.

    `is_staff` only opens the admin site's door; Django still checks a per-model
    permission on every add and change view, and these accounts have no groups.
    So a test that drives the admin over HTTP needs `superuser=True` as well, or
    the add form 403s and the POST never reaches `save_model` — which is how the
    first version of this file failed, silently creating nothing.

    **They were briefly tied together, and that broke the negative cases.**
    `is_platform_administrator` accepts a superuser *or* the ADMIN role, so a
    "staff student" who was also a superuser turned out to be an administrator
    after all, and the tests asserting a non-administrator is refused started
    passing invitations instead. The flags have to be independent for
    "staff but not entitled to admit" to be expressible.
    """
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.is_staff = staff
    user.is_superuser = superuser
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    return user


@pytest.fixture
def admin_path(settings):
    """Route the admin at a stable `/admin/` via the test-only urlconf.

    `tests/urls_with_admin.py` exists for this and says why: the real admin is
    routed only when `DJANGO_ADMIN_PATH` is set, and the path is deliberately not
    a constant anything can rely on. The first version of this fixture set
    `settings.ADMIN_PATH` and reloaded `config.urls`, which left every HTTP test
    here 404ing — and that module's own docstring reserves the reload approach for
    `test_admin_site_routing.py`, where the conditional is the thing under test.
    """
    settings.ROOT_URLCONF = "tests.urls_with_admin"
    return "/admin"


@pytest.fixture
def operator(client, admin_path):
    user = _user("operator@example.test", role=Role.ADMIN, staff=True, superuser=True)
    client.force_login(user)
    verify_admin_session(client, user.email)
    return user


class TestIssuingThroughTheAdmin:
    def test_issuing_writes_an_audit_row_naming_the_operator(self, operator) -> None:
        """The whole reason `save_model` routes through the service."""
        from apps.accounts.services import issue_invitation

        issue_invitation(actor=operator, email="guest@example.test", reason="first cohort")

        row = AuditLog.objects.get(action=AdminAction.BETA_INVITATION_ISSUED)
        assert row.actor_label == "operator@example.test"
        assert row.metadata["reason"] == "first cohort"
        assert row.metadata["invited_email"] == "guest@example.test"

    def test_the_add_form_requires_a_reason(self, operator, admin_path, client) -> None:
        """A required field answers the question in the browser.

        `issue_invitation` refuses a blank reason too, but a service exception
        reaching a `ModelAdmin` is a 500 after submitting — the form should have
        said so first.
        """
        from apps.accounts.models import BetaInvitation

        response = client.post(
            f"{admin_path}/accounts/betainvitation/add/",
            {"email": "guest@example.test"},
            follow=True,
        )

        assert response.status_code == 200
        assert not BetaInvitation.objects.exists()

    def test_adding_through_the_form_issues_and_audits(self, operator, admin_path, client) -> None:
        from apps.accounts.models import BetaInvitation

        client.post(
            f"{admin_path}/accounts/betainvitation/add/",
            {"email": "guest@example.test", "reason": "first cohort"},
            follow=True,
        )

        invitation = BetaInvitation.objects.get(email="guest@example.test")
        assert invitation.expires_at > timezone.now()
        row = AuditLog.objects.get(action=AdminAction.BETA_INVITATION_ISSUED)
        assert row.actor_label == "operator@example.test"
        assert row.target_id == str(invitation.pk)

    def test_rows_are_not_editable_after_issuing(self, operator, admin_path, client) -> None:
        """Viewable, not editable — which is Django's behaviour and the better one.

        `expires_at`, `revoked_at`, `consumed_at` and `consumed_by` belong to
        services. A change form that saved would have to decide what a hand-edited
        expiry means, and the honest answer is that it means nothing anybody
        audited.

        **The first version of this test asserted a 302 or 403 and was wrong.**
        With `has_change_permission` false but view permission present, Django
        renders the change form read-only and answers 200 — so the row stays
        auditable while staying uneditable, which is what you want for an
        admission record. Asserting the refusal instead of the read-only state
        would have pinned behaviour this admin does not have.
        """
        from apps.accounts.admin import BetaInvitationAdmin
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import issue_invitation

        invitation = issue_invitation(
            actor=operator, email="guest@example.test", reason="first cohort"
        )

        response = client.get(f"{admin_path}/accounts/betainvitation/{invitation.pk}/change/")

        assert response.status_code == 200
        # No way to submit it: Django drops the save row without change permission.
        assert b'name="_save"' not in response.content
        assert b'name="_continue"' not in response.content
        # And the permission itself, so the 200 above cannot be mistaken for
        # an editable form if Django's rendering ever changes.
        assert (
            BetaInvitationAdmin(BetaInvitation, None).has_change_permission(response.wsgi_request)
            is False
        )


class TestOnlyAdministratorsAdmit:
    @pytest.mark.parametrize("role", [Role.STUDENT, Role.INSTRUCTOR])
    def test_a_staff_non_admin_cannot_issue(self, role) -> None:
        """**Staff is not the same as administrator**, and this is the negative
        case the plan asks for by name.

        A staff account can reach the admin site; `is_platform_administrator` is
        what decides whether it may admit people. Conflating the two would let
        anybody with admin access admit learners.
        """
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import NotPermitted, issue_invitation

        actor = _user("staffer@example.test", role=role, staff=True)

        with pytest.raises(NotPermitted):
            issue_invitation(actor=actor, email="guest@example.test", reason="nope")

        assert not BetaInvitation.objects.exists()
        assert AuditLog.objects.count() == 0

    def test_a_deactivated_administrator_cannot_issue(self) -> None:
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import NotPermitted, issue_invitation

        actor = _user("former@example.test", role=Role.ADMIN, staff=True)
        actor.is_active = False
        actor.save(update_fields=["is_active"])

        with pytest.raises(NotPermitted):
            issue_invitation(actor=actor, email="guest@example.test", reason="nope")

        assert not BetaInvitation.objects.exists()


class TestTheAdminCannotCreateAccounts:
    def test_no_passwordless_user_can_be_made_here(self, operator, admin_path, client) -> None:
        """The plan's acceptance clause, asserted rather than assumed.

        `UserAdmin.has_add_permission` is `False` because an account created
        there would have no usable password and no verification email. Admission
        runs the other way round: issue an invitation, and the person registers.
        Somebody could switch this off in one line, so it is pinned.
        """
        from apps.accounts.models import User

        before = User.objects.count()
        response = client.get(f"{admin_path}/accounts/user/add/")

        assert response.status_code in (302, 403)
        assert User.objects.count() == before


class TestRevokingThroughTheAdmin:
    def test_the_action_asks_for_a_reason_before_doing_anything(
        self, operator, admin_path, client
    ) -> None:
        """A bulk action has nowhere to type one, so an intermediate page
        interposes — the same shape `CourseAdmin._with_notes` uses."""
        from apps.accounts.services import issue_invitation

        invitation = issue_invitation(
            actor=operator, email="guest@example.test", reason="first cohort"
        )

        response = client.post(
            f"{admin_path}/accounts/betainvitation/",
            {"action": "revoke_selected", "_selected_action": [str(invitation.pk)]},
        )

        assert response.status_code == 200
        assert b"Why is this being withdrawn?" in response.content
        # Nothing happened yet — the reason has not been given.
        invitation.refresh_from_db()
        assert invitation.revoked_at is None
        assert not AuditLog.objects.filter(action=AdminAction.BETA_INVITATION_REVOKED).exists()

    def test_confirming_revokes_and_audits(self, operator, admin_path, client) -> None:
        from apps.accounts.services import issue_invitation

        invitation = issue_invitation(
            actor=operator, email="guest@example.test", reason="first cohort"
        )

        client.post(
            f"{admin_path}/accounts/betainvitation/",
            {
                "action": "revoke_selected",
                "_selected_action": [str(invitation.pk)],
                "reason": "left the company",
            },
            follow=True,
        )

        invitation.refresh_from_db()
        assert invitation.revoked_at is not None
        row = AuditLog.objects.get(action=AdminAction.BETA_INVITATION_REVOKED)
        assert row.actor_label == "operator@example.test"
        assert row.metadata["reason"] == "left the company"

    def test_a_mixed_selection_revokes_what_it_can(self, operator, admin_path, client) -> None:
        """Per invitation, not in bulk.

        A selection routinely mixes states — somebody ticked several rows and one
        has since registered. The consumed one must not silently cancel the
        others, nor be dropped from the count without saying so.
        """
        from django.db import transaction

        from apps.accounts.services import consume_invitation, issue_invitation

        open_one = issue_invitation(
            actor=operator, email="open@example.test", reason="first cohort"
        )
        used = issue_invitation(actor=operator, email="used@example.test", reason="first cohort")
        learner = _user("used@example.test")
        with transaction.atomic():
            consume_invitation(user=learner)

        response = client.post(
            f"{admin_path}/accounts/betainvitation/",
            {
                "action": "revoke_selected",
                "_selected_action": [str(open_one.pk), str(used.pk)],
                "reason": "cohort cancelled",
            },
            follow=True,
        )

        assert response.status_code == 200
        open_one.refresh_from_db()
        used.refresh_from_db()
        assert open_one.revoked_at is not None
        # The consumed one is refused: an account exists, and revoking the
        # invitation would not remove its access.
        assert used.revoked_at is None
        assert AuditLog.objects.filter(action=AdminAction.BETA_INVITATION_REVOKED).count() == 1


class TestTheStateColumn:
    @pytest.mark.parametrize(
        ("setup", "expected"),
        [
            ("open", "Open"),
            ("revoked", "Revoked"),
            ("expired", "Expired"),
            ("consumed", "Used"),
        ],
    )
    def test_state_reads_the_timestamps_so_an_operator_does_not_have_to(
        self, operator, setup, expected
    ) -> None:
        """One column instead of three timestamps compared against each other.

        "Can this person still register?" should not require comparing
        `expires_at` to now while checking two nullable columns — which is
        exactly the mistake the runbook's troubleshooting table exists to catch.
        """
        from django.db import transaction

        from apps.accounts.admin import BetaInvitationAdmin
        from apps.accounts.models import BetaInvitation
        from apps.accounts.services import (
            consume_invitation,
            issue_invitation,
            revoke_invitation,
        )

        invitation = issue_invitation(
            actor=operator, email="guest@example.test", reason="first cohort"
        )

        if setup == "revoked":
            revoke_invitation(actor=operator, email="guest@example.test", reason="changed my mind")
        elif setup == "expired":
            issued = timezone.now() - timedelta(days=40)
            BetaInvitation.objects.filter(pk=invitation.pk).update(
                created_at=issued, expires_at=issued + timedelta(days=30)
            )
        elif setup == "consumed":
            learner = _user("guest@example.test")
            with transaction.atomic():
                consume_invitation(user=learner)

        invitation.refresh_from_db()
        rendered = BetaInvitationAdmin(BetaInvitation, None).state(invitation)

        assert rendered == expected
