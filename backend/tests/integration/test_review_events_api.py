"""The review trail an instructor can read.

The security-critical test here is the boring-looking one: the route must
refuse writes. A review event is the record of an admin's decision, so an
instructor who could POST one could write themselves an approval — and since
nothing downstream re-derives publication from the trail, the forgery would
not be caught by anything else. `test_the_trail_is_not_writable` provokes each
verb rather than trusting that a read-only base class was used.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _course(slug: str, owner_email: str):
    from apps.catalog.models import Course, Language

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Español"}
    )
    return Course.objects.create(
        slug=slug,
        title=slug,
        language=language,
        level="A1",
        instructor=_user(owner_email, Role.INSTRUCTOR),
    )


@pytest.fixture
def mine(db):
    return _course("mine", "me@example.test")


@pytest.fixture
def theirs(db):
    return _course("theirs", "them@example.test")


def _sign_in(client, email: str):
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _events_url(course) -> str:
    return f"/api/v1/instructor/courses/{course.id}/review-events/"


def _submit_url(course) -> str:
    return f"/api/v1/instructor/courses/{course.id}/submit-for-review/"


@pytest.mark.django_db
class TestSubmissionIsRecorded:
    def test_submitting_writes_an_event_naming_the_instructor(self, client, mine) -> None:
        """Without this the trail cannot say when a course entered the queue,
        which is what T7 orders on."""
        from apps.catalog.models import CourseReviewEvent

        _sign_in(client, "me@example.test")

        client.post(_submit_url(mine))

        event = CourseReviewEvent.objects.get(course=mine)
        assert event.action == "SUBMITTED"
        assert event.actor == mine.instructor

    def test_a_rejected_course_resubmitted_keeps_both_records(self, client, mine) -> None:
        """The reject-fix-resubmit loop is history, not a field to overwrite."""
        from apps.catalog.models import CourseReviewEvent
        from apps.catalog.services import reject

        admin = _user("admin@example.test", Role.ADMIN)
        _sign_in(client, "me@example.test")

        client.post(_submit_url(mine))
        mine.refresh_from_db()
        reject(course=mine, by=admin, notes="Audio is inaudible in lesson 3.")
        client.post(_submit_url(mine))

        actions = list(
            CourseReviewEvent.objects.filter(course=mine)
            .order_by("created_at")
            .values_list("action", flat=True)
        )
        assert actions == ["SUBMITTED", "REJECTED", "SUBMITTED"]

    def test_a_failed_submission_records_nothing(self, client, mine) -> None:
        """Submitting twice is a 409; the refused attempt must not land in the
        trail, or the queue order becomes a lie."""
        from apps.catalog.models import CourseReviewEvent

        _sign_in(client, "me@example.test")
        client.post(_submit_url(mine))

        assert client.post(_submit_url(mine)).status_code == 409
        assert CourseReviewEvent.objects.filter(course=mine).count() == 1


@pytest.mark.django_db
class TestReadingTheTrail:
    def test_the_instructor_can_read_the_notes_on_a_rejection(self, client, mine) -> None:
        """The whole reason `notes` exists. A rejection an instructor cannot
        read tells them nothing to fix."""
        from apps.catalog.services import reject, submit_for_review

        admin = _user("admin@example.test", Role.ADMIN)
        submit_for_review(course=mine, by=mine.instructor)
        reject(course=mine, by=admin, notes="Audio is inaudible in lesson 3.")
        _sign_in(client, "me@example.test")

        body = client.get(_events_url(mine)).json()

        assert body["results"][0]["notes"] == "Audio is inaudible in lesson 3."

    def test_the_newest_decision_comes_first(self, client, mine) -> None:
        from apps.catalog.services import reject, submit_for_review

        admin = _user("admin@example.test", Role.ADMIN)
        submit_for_review(course=mine, by=mine.instructor)
        reject(course=mine, by=admin)
        _sign_in(client, "me@example.test")

        actions = [row["action"] for row in client.get(_events_url(mine)).json()["results"]]

        assert actions[0] == "REJECTED"

    def test_reading_another_instructors_trail_is_a_404(self, client, mine, theirs) -> None:
        from apps.catalog.services import submit_for_review

        submit_for_review(course=theirs, by=theirs.instructor)
        _sign_in(client, "me@example.test")

        assert client.get(_events_url(theirs)).status_code == 404


@pytest.mark.django_db
class TestTheTrailIsNotWritable:
    """An instructor who could write here could approve their own course."""

    def test_the_trail_is_not_writable(self, client, mine) -> None:
        from apps.catalog.models import CourseReviewEvent
        from apps.catalog.services import reject, submit_for_review

        admin = _user("admin@example.test", Role.ADMIN)
        submit_for_review(course=mine, by=mine.instructor)
        reject(course=mine, by=admin, notes="Original.")
        existing = CourseReviewEvent.objects.get(course=mine, action="REJECTED")
        _sign_in(client, "me@example.test")

        forged = {"action": "APPROVED", "notes": "Looks great to me."}
        responses = {
            "post": client.post(
                _events_url(mine), forged, content_type="application/json"
            ).status_code,
            "patch": client.patch(
                f"{_events_url(mine)}{existing.id}/", forged, content_type="application/json"
            ).status_code,
            "delete": client.delete(f"{_events_url(mine)}{existing.id}/").status_code,
        }

        assert all(code == 405 for code in responses.values()), responses
        existing.refresh_from_db()
        assert existing.action == "REJECTED"
        assert existing.notes == "Original."
        assert not CourseReviewEvent.objects.filter(action="APPROVED").exists()

    def test_publication_still_requires_an_admin(self, client, mine) -> None:
        """The forgery above would only matter if something downstream trusted
        the trail. Nothing does — publication runs through the state machine —
        and this pins that down."""
        from apps.catalog.models import CourseReviewEvent, CourseStatus

        CourseReviewEvent.objects.create(
            course=mine,
            actor=mine.instructor,
            action=CourseReviewEvent.Action.APPROVED,
            notes="Self-approved.",
        )
        mine.refresh_from_db()

        assert mine.status == CourseStatus.DRAFT
