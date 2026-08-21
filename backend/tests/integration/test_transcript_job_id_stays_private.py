"""Abuse case 11: the provider's job id reaches no learner.

Swept rather than spot-checked, for the reason M5 learned twice: a leak is a
property of the system, and checking the endpoint you happened to think of is
how the next one leaks.

The job id is a support handle. It identifies our account's work at a
third party, it is what a callback is matched on, and it has no use anywhere a
learner or another instructor can read — which makes "it appears in no
response" a stronger and simpler property than "it appears only where it
should".
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.transcripts.models import Transcript, TranscriptSegment, TranscriptStatus

PASSWORD = "a-long-enough-passphrase"
JOB_ID = "fakejob_support_handle_only"

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


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test", Role.INSTRUCTOR)


@pytest.fixture
def published(db, instructor):
    """A published lesson with an approved transcript."""
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    asset = MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
    )
    transcript = Transcript.objects.create(
        media_asset=asset,
        language=language,
        provider="fake",
        provider_job_id=JOB_ID,
        status=TranscriptStatus.APPROVED,
        reviewed_by=instructor,
        approved_at=timezone.now(),
    )
    TranscriptSegment.objects.create(
        transcript=transcript, position=1, start_ms=0, end_ms=1500, text="Buenos días."
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return course, lesson, transcript


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _every_readable_path(course, lesson, transcript) -> list[str]:
    return [
        "/api/v1/catalogue/courses/",
        f"/api/v1/catalogue/courses/{course.slug}/",
        f"/api/v1/lessons/{lesson.id}/",
        f"/api/v1/lessons/{lesson.id}/transcript.vtt",
        f"/api/v1/transcripts/{transcript.id}/",
        "/api/v1/auth/me/",
    ]


class TestTheJobIdIsNeverReturned:
    def test_not_to_an_entitled_subscriber(self, client, published) -> None:
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        course, lesson, transcript = published
        subscriber = _user("payer@example.test")
        start_subscription(user=subscriber, provider=FakeBillingProvider())
        _sign_in(client, "payer@example.test")

        for path in _every_readable_path(course, lesson, transcript):
            assert JOB_ID.encode() not in client.get(path).content, path

    def test_not_to_an_anonymous_visitor(self, client, published) -> None:
        course, lesson, transcript = published

        for path in _every_readable_path(course, lesson, transcript):
            assert JOB_ID.encode() not in client.get(path).content, path

    def test_not_even_to_the_instructor_who_owns_it(self, client, published) -> None:
        """The most tempting place to expose it, and still no. The review
        screen has no use for a provider handle, and a field that appears
        where it is not needed is a field that leaks where it is not
        checked."""
        course, lesson, transcript = published
        _sign_in(client, "teacher@example.test")

        for path in _every_readable_path(course, lesson, transcript):
            assert JOB_ID.encode() not in client.get(path).content, path

    def test_the_serializer_has_no_such_field(self) -> None:
        """Structural, so it cannot be added back by widening `fields`."""
        from apps.transcripts.serializers import TranscriptSerializer

        assert "provider_job_id" not in TranscriptSerializer().fields
        assert "provider" not in TranscriptSerializer().fields

    def test_it_is_still_stored(self, published) -> None:
        """The positive twin. A migration dropping the column would satisfy
        every test above and break the callback that matches on it."""
        _, _, transcript = published

        transcript.refresh_from_db()
        assert transcript.provider_job_id == JOB_ID
