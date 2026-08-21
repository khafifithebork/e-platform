"""The M7 abuse cases nothing else covers.

Most of the ten are proven where they live:

- **3** entitlement gates recording — `test_progress_recording.py`
  (`TestEntitlementIsCheckedBesideTheWrite`) and `test_progress_endpoint.py`.
- **4** another learner's progress is unreachable — `test_progress_endpoint.py`
  (`TestProgressIsAlwaysYourOwn`); the route carries no learner to tamper with.
- **5** upserted, not appended — `test_progress_recording.py`
  (`test_two_hundred_heartbeats_are_still_one_row`).
- **6** `max_position_seconds` never moves backwards — same file
  (`test_rewinding_does_not_move_it_back`), plus the database constraint.
- **7** a completed lesson stays completed — same file
  (`test_rewatching_does_not_un_complete`).
- **8** only APPROVED transcripts are served — `test_transcript_panel.py`, swept
  across every lesson-scoped route.
- **9** completion is defined once — `test_course_completion.py`
  (`TestTheRuleLivesInOnePlace`), an AST guard.
- **10** progress writes are throttled — `test_throttling.py`, in the module
  with real rates, because a per-test override of `THROTTLE_RATES` never
  applies.

**Cases 1 and 2 are here**, and the spec calls the first the single most
important test in the milestone. Both say the same thing from opposite sides:
an `Enrollment` is a record of what somebody watched and never an input to an
access decision (ADR-016 §1, invariant 3).

They are swept across every learner-facing route rather than checked on the
endpoint that came to mind. "You must be enrolled to watch" is a rule that
sounds ordinary and would be a second entitlement implementation; if it ever
gets written, it will be written in one view, and a spot-check tests the other
one.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.entitlements.resolver import resolve_access
from apps.learning.models import Enrollment

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _subscribe(user):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    start_subscription(user=user, provider=FakeBillingProvider())
    return user


@pytest.fixture
def lesson(db):
    from django.utils import timezone

    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review
    from apps.media_assets.models import MediaAsset, MediaAssetStatus
    from apps.transcripts.models import (
        Transcript,
        TranscriptKind,
        TranscriptSegment,
        TranscriptStatus,
    )

    instructor = _user("teacher@example.test", Role.INSTRUCTOR)
    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
        duration_seconds=600,
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)

    transcript = Transcript.objects.create(
        media_asset=lesson.media_asset,
        language=language,
        kind=TranscriptKind.TARGET,
        status=TranscriptStatus.APPROVED,
        provider="fake",
        provider_job_id="job-abuse",
        reviewed_by=admin,
        approved_at=timezone.now(),
    )
    TranscriptSegment.objects.create(
        transcript=transcript, position=1, start_ms=0, end_ms=2000, text="hola"
    )
    return lesson


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _gated_requests(client, lesson) -> dict[str, int]:
    """Every learner-facing route that costs money to reach, by status code.

    Listed rather than walked, unlike the transcript sweep, because these are
    not all GETs and each needs its own body — but the list is the point: a
    control asserted on one of them proves nothing about the other four.
    """
    return {
        "playback-token": client.post(f"/api/v1/lessons/{lesson.id}/playback-token/").status_code,
        "lesson-body": client.get(f"/api/v1/lessons/{lesson.id}/").status_code,
        "transcript-panel": client.get(f"/api/v1/lessons/{lesson.id}/transcript/").status_code,
        "subtitles": client.get(f"/api/v1/lessons/{lesson.id}/transcript.vtt").status_code,
        "record-progress": client.put(
            f"/api/v1/lessons/{lesson.id}/progress/",
            {"position_seconds": 30, "watched_delta_seconds": 15},
            content_type="application/json",
        ).status_code,
        "mark-complete": client.post(f"/api/v1/lessons/{lesson.id}/complete/").status_code,
    }


class TestCase1EnrollingGrantsNothing:
    """The single most important test in this milestone (spec §4).

    The rule it protects against is tempting because it sounds ordinary:
    *"you must be enrolled to watch"*. It is a second entitlement
    implementation, and the two disagree the first time a subscription lapses
    while the enrolment row survives — which it does by design, because it
    holds the learner's progress.
    """

    def test_an_enrolment_opens_no_door(self, client, lesson) -> None:
        learner = _user("broke@example.test")
        Enrollment.objects.create(user=learner, course=lesson.course, last_lesson=lesson)
        _sign_in(client, "broke@example.test")

        statuses = _gated_requests(client, lesson)

        assert all(status == 403 for status in statuses.values()), statuses

    def test_the_same_learner_is_let_in_once_they_pay(self, client, lesson) -> None:
        """The positive twin, and it is doing real work here: a route that
        refused everybody would satisfy the test above completely."""
        learner = _user("payer@example.test")
        Enrollment.objects.create(user=learner, course=lesson.course, last_lesson=lesson)
        _subscribe(learner)
        _sign_in(client, "payer@example.test")

        statuses = _gated_requests(client, lesson)

        assert all(status == 200 for status in statuses.values()), statuses

    def test_the_resolver_gives_the_same_answer_either_way(self, lesson) -> None:
        """Under the endpoints, at the one place access is decided.

        Asserted on the *reason*, not on the boolean: a decision that flipped
        to allowed for a new reason would still be a second entitlement rule.
        """
        learner = _user("nobody@example.test")

        before = resolve_access(user=learner, lesson=lesson)
        Enrollment.objects.create(user=learner, course=lesson.course, last_lesson=lesson)
        after = resolve_access(user=learner, lesson=lesson)

        assert (before.allowed, before.reason) == (after.allowed, after.reason)
        assert not after.allowed

    def test_enrolling_in_one_course_opens_nothing_in_another(self, client, lesson) -> None:
        """The cross-course form. An enrolment is not even a weak signal about
        a different course, and a rule keyed on "has any enrolment" would pass
        every test above."""
        from apps.catalog.models import Course, Lesson, Section

        other = Course.objects.create(
            slug="french",
            title="French",
            language=lesson.course.language,
            level="A1",
            instructor=lesson.course.instructor,
        )
        other_section = Section.objects.create(course=other, title="Bonjour", position=1)
        other_lesson = Lesson.objects.create(
            course=other, section=other_section, slug="bonjour", title="Bonjour", position=1
        )
        learner = _user("broke@example.test")
        Enrollment.objects.create(user=learner, course=lesson.course, last_lesson=lesson)

        assert not resolve_access(user=learner, lesson=other_lesson).allowed


class TestCase2UnEnrollingTakesNothingAway:
    """The other side of the same rule.

    If enrolment ever became an input to access, this is the test that would
    fail rather than the one above — a permissive bug reads as working software
    until somebody's row is deleted.
    """

    def test_deleting_the_enrolment_leaves_access_intact(self, client, lesson) -> None:
        learner = _subscribe(_user("learner@example.test"))
        _sign_in(client, "learner@example.test")
        # Enrol the way production does — by watching — so the row under test
        # is the one the service actually writes.
        client.put(
            f"/api/v1/lessons/{lesson.id}/progress/",
            {"position_seconds": 30, "watched_delta_seconds": 15},
            content_type="application/json",
        )
        assert Enrollment.objects.filter(user=learner).exists()

        Enrollment.objects.filter(user=learner).delete()

        statuses = _gated_requests(client, lesson)
        assert all(status == 200 for status in statuses.values()), statuses

    def test_and_the_resolver_does_not_notice(self, lesson) -> None:
        learner = _subscribe(_user("learner@example.test"))
        Enrollment.objects.create(user=learner, course=lesson.course, last_lesson=lesson)

        with_enrolment = resolve_access(user=learner, lesson=lesson)
        Enrollment.objects.filter(user=learner).delete()
        without = resolve_access(user=learner, lesson=lesson)

        assert (with_enrolment.allowed, with_enrolment.reason) == (without.allowed, without.reason)
        assert without.allowed

    def test_progress_is_what_is_actually_lost(self, client, lesson) -> None:
        """What deleting an enrolment *does* cost, stated so the guarantee
        above is not read as "the row does nothing". It holds the bookmark and
        the course completion date, and those do go."""
        learner = _subscribe(_user("learner@example.test"))
        _sign_in(client, "learner@example.test")
        client.put(
            f"/api/v1/lessons/{lesson.id}/progress/",
            {"position_seconds": 30, "watched_delta_seconds": 15},
            content_type="application/json",
        )

        Enrollment.objects.filter(user=learner).delete()

        body = client.get("/api/v1/me/courses/").json()
        assert body["results"] == []
        # The lesson-level progress survives, because it hangs off the lesson
        # rather than the enrolment. Only the course-level bookmark is gone.
        assert client.get(f"/api/v1/lessons/{lesson.id}/progress/").json()["watched_seconds"] == 15
