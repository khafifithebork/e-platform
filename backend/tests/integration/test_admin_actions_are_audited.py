"""§8: every admin action writes an audit row.

T4 covered the access override. This covers the two that already existed
before M10 — course approval and role change — plus the surface role change
needed, since there was no way to change a role at all except the shell.

The rows written here are *not* duplicates of `CourseReviewEvent` (ADR-018 §8).
That is the course's own history, shown to the instructor who submitted it.
This is the administrative trail, read while answering "what has this account
done, and who did it".
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.core.audit import AdminAction
from apps.core.models import AuditLog
from tests.otp_helpers import verify_admin_session

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, *, role: str = Role.STUDENT, staff: bool = False):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.is_staff = staff
    user.save(update_fields=["role", "is_staff"])
    return user


@pytest.fixture
def admin_user(db):
    return _user("admin@example.test", role=Role.ADMIN, staff=True)


@pytest.fixture
def submitted_course(db, admin_user):
    from apps.catalog.models import Course, Language
    from apps.catalog.services import submit_for_review

    instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    submit_for_review(course=course, by=instructor)
    return course


class TestCourseReviewIsAudited:
    def test_approving_writes_a_row(self, admin_user, submitted_course) -> None:
        from apps.catalog.services import approve

        approve(course=submitted_course, by=admin_user)

        row = AuditLog.objects.get()
        assert row.action == AdminAction.COURSE_APPROVED
        assert (row.target_type, row.target_id) == ("course", str(submitted_course.pk))
        assert row.actor_label == "admin@example.test"
        assert row.metadata["course_slug"] == "spanish"

    def test_an_approval_without_notes_says_so(self, admin_user, submitted_course) -> None:
        """Rather than a template like "approved for publication", which would
        read as a justification nobody gave. M3 does not ask for notes on an
        approval and this does not pretend otherwise."""
        from apps.catalog.services import approve

        approve(course=submitted_course, by=admin_user)

        assert AuditLog.objects.get().metadata["reason"] == "Approved with no notes recorded"

    def test_an_approval_with_notes_keeps_them(self, admin_user, submitted_course) -> None:
        from apps.catalog.services import approve

        approve(course=submitted_course, by=admin_user, notes="Checked the audio quality")

        assert AuditLog.objects.get().metadata["reason"] == "Checked the audio quality"

    def test_rejecting_writes_the_reviewer_s_words(self, admin_user, submitted_course) -> None:
        from apps.catalog.services import reject

        reject(course=submitted_course, by=admin_user, notes="Lesson 3 has no audio")

        row = AuditLog.objects.get()
        assert row.action == AdminAction.COURSE_REJECTED
        assert row.metadata["reason"] == "Lesson 3 has no audio"

    def test_requesting_changes_is_a_different_action(self, admin_user, submitted_course) -> None:
        """Same transition, different decision on the record — and the audit
        trail has to tell them apart, because an instructor sent back to fix
        one thing is not an instructor turned down."""
        from apps.catalog.services import request_changes

        request_changes(course=submitted_course, by=admin_user, notes="Retake lesson 2")

        assert AuditLog.objects.get().action == AdminAction.COURSE_CHANGES_REQUESTED

    def test_the_course_history_is_written_too(self, admin_user, submitted_course) -> None:
        """Both rows, on purpose. Neither replaces the other."""
        from apps.catalog.models import CourseReviewEvent
        from apps.catalog.services import approve

        approve(course=submitted_course, by=admin_user)

        assert CourseReviewEvent.objects.filter(action="APPROVED").count() == 1
        assert AuditLog.objects.filter(action=AdminAction.COURSE_APPROVED).count() == 1

    def test_a_refused_approval_writes_nothing(self, submitted_course) -> None:
        """The twin. An audit row for an action that did not happen is a false
        record, and the transaction is what prevents it."""
        from apps.catalog.services import NotPermitted, approve

        with pytest.raises(NotPermitted):
            approve(course=submitted_course, by=_user("nobody@example.test"))

        assert not AuditLog.objects.exists()


class TestApprovingThroughTheAdminSiteIsAudited:
    """End to end through the admin action, which is the surface approvals
    actually happen on. The service records; the view supplies only the
    address, which is the one thing a service cannot know."""

    def test_the_address_is_recorded(self, client, admin_user, submitted_course, settings) -> None:
        settings.ROOT_URLCONF = "tests.urls_with_admin"
        # Django's own model permissions gate the changelist, and this project
        # grants none — so reaching an admin page at all means superuser, the
        # same setup the M3 review-queue tests use.
        admin_user.is_superuser = True
        admin_user.save(update_fields=["is_superuser"])
        client.force_login(admin_user)
        verify_admin_session(client, "admin@example.test")

        response = client.post(
            "/admin/catalog/course/",
            {"action": "approve_selected", "_selected_action": [str(submitted_course.pk)]},
            REMOTE_ADDR="203.0.113.9",
            follow=True,
        )

        assert response.status_code == 200
        row = AuditLog.objects.get()
        assert row.action == AdminAction.COURSE_APPROVED
        assert row.ip_address == "203.0.113.9"

    def test_and_the_course_was_actually_published(
        self, client, admin_user, submitted_course, settings
    ) -> None:
        """The twin. A POST that silently did nothing would leave no audit row
        either, and the test above would report the wrong reason for it."""
        settings.ROOT_URLCONF = "tests.urls_with_admin"
        admin_user.is_superuser = True
        admin_user.save(update_fields=["is_superuser"])
        client.force_login(admin_user)
        verify_admin_session(client, "admin@example.test")

        client.post(
            "/admin/catalog/course/",
            {"action": "approve_selected", "_selected_action": [str(submitted_course.pk)]},
            follow=True,
        )
        submitted_course.refresh_from_db()

        assert submitted_course.status == "PUBLISHED"


class TestRoleChangeIsAudited:
    def test_it_records_where_the_role_moved_from_and_to(self, admin_user) -> None:
        from apps.accounts.services import change_role

        learner = _user("learner@example.test")

        change_role(
            actor=admin_user,
            user=learner,
            role=Role.INSTRUCTOR,
            reason="Approved as an instructor",
        )

        row = AuditLog.objects.get()
        assert row.action == AdminAction.ROLE_CHANGED
        assert (row.target_type, row.target_id) == ("user", str(learner.pk))
        assert row.metadata["previous_role"] == Role.STUDENT
        assert row.metadata["new_role"] == Role.INSTRUCTOR

    def test_the_role_actually_changes(self, admin_user) -> None:
        """The twin. A service that audited without writing would satisfy the
        test above."""
        from apps.accounts.services import change_role

        learner = _user("learner@example.test")

        change_role(actor=admin_user, user=learner, role=Role.INSTRUCTOR, reason="Because")
        learner.refresh_from_db()

        assert learner.role == Role.INSTRUCTOR

    def test_a_no_op_is_refused(self, admin_user) -> None:
        """A trail full of "changed from student to student" is one nobody
        reads."""
        from apps.accounts.services import RoleUnchanged, change_role

        learner = _user("learner@example.test")

        with pytest.raises(RoleUnchanged):
            change_role(actor=admin_user, user=learner, role=Role.STUDENT, reason="Because")

        assert not AuditLog.objects.exists()

    def test_an_unknown_role_is_refused(self, admin_user) -> None:
        from apps.accounts.services import InvalidRole, change_role

        learner = _user("learner@example.test")

        with pytest.raises(InvalidRole):
            change_role(actor=admin_user, user=learner, role="SUPERVISOR", reason="Because")

        learner.refresh_from_db()
        assert learner.role == Role.STUDENT
        assert not AuditLog.objects.exists()

    def test_it_never_grants_staff(self, admin_user) -> None:
        """`is_staff` is the admin site's own gate and a wider capability than
        any role. Granting it through a role dropdown would erase the
        distinction accounts.models draws deliberately."""
        from apps.accounts.services import change_role

        learner = _user("learner@example.test")

        change_role(actor=admin_user, user=learner, role=Role.ADMIN, reason="Because")
        learner.refresh_from_db()

        assert learner.role == Role.ADMIN
        assert learner.is_staff is False


class TestTheUserAdminIsNarrow:
    def test_it_exposes_no_privilege_fields(self) -> None:
        """The account table decides who is an administrator. A `ModelAdmin`
        with the defaults on would let anyone with admin access tick
        `is_superuser`."""
        from django.contrib import admin as django_admin

        from apps.accounts.models import User

        editable = set(django_admin.site._registry[User].fields) - set(
            django_admin.site._registry[User].readonly_fields
        )

        assert editable == {"role", "is_active"}

    def test_accounts_cannot_be_added_or_deleted_here(self) -> None:
        from django.contrib import admin as django_admin

        from apps.accounts.models import User

        model_admin = django_admin.site._registry[User]

        assert model_admin.has_add_permission(None) is False
        assert model_admin.has_delete_permission(None) is False

    def test_an_administrator_cannot_change_their_own_role(self, rf, admin_user) -> None:
        """Self-service privilege change is the shape most worth making
        awkward. Another administrator can do it, and the audit row will name
        them."""
        from django.contrib import admin as django_admin

        from apps.accounts.models import User

        request = rf.get("/")
        request.user = admin_user
        model_admin = django_admin.site._registry[User]

        assert "role" in model_admin.get_readonly_fields(request, obj=admin_user)

    def test_but_can_change_somebody_else_s(self, rf, admin_user) -> None:
        """The twin. A readonly rule that applied to everyone would satisfy
        the test above and make the screen useless."""
        from django.contrib import admin as django_admin

        from apps.accounts.models import User

        request = rf.get("/")
        request.user = admin_user
        model_admin = django_admin.site._registry[User]

        assert "role" not in model_admin.get_readonly_fields(
            request, obj=_user("someone@example.test")
        )
