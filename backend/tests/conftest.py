"""Shared test fixtures."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone


@pytest.fixture(autouse=True)
def _clear_throttle_state():
    """Reset the cache between tests.

    DRF throttling counts requests in the default cache, which lives for the
    whole test process. Without this the counters accumulate across unrelated
    tests until the shared `anon` bucket is exhausted, and the failures land on
    whichever test happened to run once the limit was reached — a test that
    passes alone and fails in the suite, which is the worst kind.

    Autouse rather than opt-in: a test that needs this and does not know it is
    exactly the case that goes unnoticed.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def transcript_factory(db):
    """A transcript at a chosen status and age.

    Shared, because a transcript needs a language, an instructor, a course, a
    section, a lesson and a media asset behind it, and two files now want one:
    the metrics tests and the stuck-transcription alert. It started local to
    the first and moved here when the second arrived, rather than being
    duplicated.

    The titles and addresses are deliberately distinctive, because the alert
    tests assert that none of them reaches an operational email.
    """
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Role
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.media_assets.models import MediaAsset, MediaAssetStatus
    from apps.transcripts.models import Transcript, TranscriptStatus

    instructor = get_user_model().objects.create_user(
        email="metrics-instructor@example.test",
        password="irrelevant-to-this-test",
        role=Role.INSTRUCTOR,
    )
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="metrics-spanish",
        title="Spanish",
        language=language,
        level="A1",
        instructor=instructor,
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)

    created: list = []

    def make(*, status, age: timedelta):
        position = len(created) + 1
        lesson = Lesson.objects.create(
            course=course,
            section=section,
            slug=f"lesson-{position}",
            title=f"Lesson {position}",
            position=position,
        )
        asset = MediaAsset.objects.create(
            lesson=lesson,
            source_object_key=f"masters/{position}/a.mp4",
            source_bytes=2048,
            provider="fake",
            provider_asset_id=f"fakeasset_{position}",
            provider_playback_id=f"fakeplay_{position}",
            status=MediaAssetStatus.READY,
        )
        # An APPROVED transcript must carry its reviewer and approval time —
        # a database CheckConstraint, not a Python validator (invariant 11), and
        # it refused the first version of this factory.
        signature = (
            {"reviewed_by": instructor, "approved_at": timezone.now()}
            if status == TranscriptStatus.APPROVED
            else {}
        )
        transcript = Transcript.objects.create(
            media_asset=asset,
            language=language,
            provider="fake",
            provider_job_id=f"fakejob_{position}",
            status=status,
            **signature,
        )
        # created_at is auto_now_add, so the age has to be applied afterwards,
        # and with update() rather than save() so auto_now fields do not undo it.
        Transcript.objects.filter(pk=transcript.pk).update(created_at=timezone.now() - age)
        created.append(transcript)
        return transcript

    return make
