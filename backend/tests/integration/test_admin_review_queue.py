"""The admin review queue.

Two things are being proven here beyond "the buttons work".

The first is that Django's ``is_staff`` and this product's ``role == ADMIN``
are different facts. Admin access is granted by the former; publishing is
authorised by the latter, in ``services.py``. A staff account without the role
must be able to open the queue and still publish nothing — otherwise the day
someone is given staff access to fix a typo is the day they can approve
courses.

The second is that the trail cannot be edited through the admin. An editable
audit trail looks like evidence while being whatever the last person with
access decided it should say.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"
COURSES_CHANGELIST = "/admin/catalog/course/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _admin_is_routed(settings):
    """Routes admin for this module only.

    Assigning ROOT_URLCONF through the settings fixture fires
    setting_changed, which clears Django's URL caches — the real urlconf is
    untouched and every other test still cannot reach admin.
    """
    settings.ROOT_URLCONF = "tests.urls_with_admin"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str, *, staff: bool):
    """Staff accounts are superusers here on purpose.

    Django model permissions are not the control being tested — granting the
    full set makes the point sharper, because the staff-without-the-role
    account then has every permission Django can give and still publishes
    nothing.
    """
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.is_staff = staff
    user.is_superuser = staff
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    return user


@pytest.fixture
def admin_user(db):
    return _user("admin@example.test", Role.ADMIN, staff=True)


@pytest.fixture
def submitted_course(db):
    """A course sitting in the queue, submitted by its instructor."""
    from apps.catalog.models import Course, Language
    from apps.catalog.services import submit_for_review

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Español"}
    )
    instructor = _user("teacher@example.test", Role.INSTRUCTOR, staff=False)
    course = Course.objects.create(
        slug="waiting", title="Waiting", language=language, level="A1", instructor=instructor
    )
    submit_for_review(course=course, by=instructor)
    return course


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _act(client, action: str, course, **extra):
    return client.post(
        COURSES_CHANGELIST,
        {"action": action, "_selected_action": [str(course.pk)], **extra},
        follow=True,
    )


class TestStaffIsNotTheSameAsAdmin:
    def test_a_staff_account_without_the_role_publishes_nothing(
        self, client, submitted_course
    ) -> None:
        """The control is in services.py, so the admin cannot route around it."""
        from apps.catalog.models import CourseStatus

        _user("helper@example.test", Role.STUDENT, staff=True)  # every Django permission
        _sign_in(client, "helper@example.test")

        _act(client, "approve_selected", submitted_course)

        submitted_course.refresh_from_db()
        assert submitted_course.status == CourseStatus.IN_REVIEW

    def test_a_non_staff_account_cannot_reach_the_queue_at_all(
        self, client, submitted_course
    ) -> None:
        _sign_in(client, "teacher@example.test")

        response = client.get(COURSES_CHANGELIST)

        assert response.status_code in (302, 403)


class TestApproval:
    def test_approving_publishes_and_records_the_reviewer(
        self, client, admin_user, submitted_course
    ) -> None:
        from apps.catalog.models import CourseReviewEvent, CourseStatus

        _sign_in(client, "admin@example.test")

        _act(client, "approve_selected", submitted_course)

        submitted_course.refresh_from_db()
        assert submitted_course.status == CourseStatus.PUBLISHED
        assert submitted_course.published_at is not None
        event = CourseReviewEvent.objects.get(course=submitted_course, action="APPROVED")
        assert event.actor == admin_user

    def test_a_course_not_in_review_is_reported_not_published(
        self, client, admin_user, submitted_course
    ) -> None:
        """A selection routinely mixes states. One course that cannot move must
        be reported, not silently skipped and not published anyway."""
        from apps.catalog.models import CourseStatus

        _sign_in(client, "admin@example.test")
        _act(client, "approve_selected", submitted_course)

        response = _act(client, "approve_selected", submitted_course)

        submitted_course.refresh_from_db()
        assert submitted_course.status == CourseStatus.PUBLISHED
        assert b"cannot do that from" in response.content


class TestRejectionCarriesNotes:
    def test_the_first_post_asks_for_notes_and_changes_nothing(
        self, client, admin_user, submitted_course
    ) -> None:
        from apps.catalog.models import CourseStatus

        _sign_in(client, "admin@example.test")

        response = _act(client, "reject_selected", submitted_course)

        assert b'name="notes"' in response.content
        submitted_course.refresh_from_db()
        assert submitted_course.status == CourseStatus.IN_REVIEW

    def test_confirming_with_notes_returns_it_to_draft_with_the_reason(
        self, client, admin_user, submitted_course
    ) -> None:
        from apps.catalog.models import CourseReviewEvent, CourseStatus

        _sign_in(client, "admin@example.test")

        _act(
            client,
            "reject_selected",
            submitted_course,
            notes="Audio is inaudible in lesson 3.",
        )

        submitted_course.refresh_from_db()
        assert submitted_course.status == CourseStatus.DRAFT
        event = CourseReviewEvent.objects.get(course=submitted_course, action="REJECTED")
        assert event.notes == "Audio is inaudible in lesson 3."


class TestTheTrailIsNotEditableInAdmin:
    def test_the_add_page_is_refused(self, client, admin_user, submitted_course) -> None:
        _sign_in(client, "admin@example.test")

        assert client.get("/admin/catalog/coursereviewevent/add/").status_code == 403

    def test_the_change_page_is_read_only(self, client, admin_user, submitted_course) -> None:
        """Django serves the change view for a no-change model, but as a
        read-only page — a POST to it must alter nothing."""
        from apps.catalog.models import CourseReviewEvent

        event = CourseReviewEvent.objects.get(course=submitted_course)
        _sign_in(client, "admin@example.test")

        client.post(
            f"/admin/catalog/coursereviewevent/{event.pk}/change/",
            {"action": "APPROVED", "notes": "Rewritten."},
        )

        event.refresh_from_db()
        assert event.action == "SUBMITTED"
        assert event.notes == ""

    def test_the_delete_page_is_refused(self, client, admin_user, submitted_course) -> None:
        from apps.catalog.models import CourseReviewEvent

        event = CourseReviewEvent.objects.get(course=submitted_course)
        _sign_in(client, "admin@example.test")

        response = client.post(f"/admin/catalog/coursereviewevent/{event.pk}/delete/")

        assert response.status_code == 403
        assert CourseReviewEvent.objects.filter(pk=event.pk).exists()


class TestTheQueueIsAQueue:
    def test_it_is_ordered_by_submission_not_by_last_edit(
        self, client, admin_user, submitted_course
    ) -> None:
        """The reason submissions are events. If the queue ordered on
        updated_at, an instructor could jump it by editing a title."""
        from apps.catalog.models import Course
        from apps.catalog.services import submit_for_review

        later = Course.objects.create(
            slug="later",
            title="Later",
            language=submitted_course.language,
            level="A1",
            instructor=submitted_course.instructor,
        )
        submit_for_review(course=later, by=later.instructor)

        # The earlier submission is touched after the later one was made.
        submitted_course.title = "Waiting, edited"
        submitted_course.save(update_fields=["title", "updated_at"])

        _sign_in(client, "admin@example.test")
        body = client.get(COURSES_CHANGELIST).content

        assert body.index(b"Waiting, edited") < body.index(b"Later")
