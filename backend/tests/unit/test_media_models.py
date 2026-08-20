"""MediaAsset, WebhookEvent, and the constraints that hold them true.

Invariant 11: these are database constraints, not validators, so every test
writes a row the database must reject. Same discipline as M4's — the exception
is matched by constraint *name*, because a bare IntegrityError would pass when
some other constraint refused the row and leave the intended one untested.

The one worth reading twice is `TestAPlaybackUrlCannotBeStored`. Invariant 7
says never store a playback URL, and until now that was a rule people had to
remember. It is a `CheckConstraint` here, so the database refuses.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, role: str = Role.INSTRUCTOR):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def lesson(db):
    from apps.catalog.models import Course, Language, Lesson, Section

    instructor = _user("teacher@example.test")
    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    return Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )


@pytest.fixture
def second_lesson(db, lesson):
    from apps.catalog.models import Lesson

    return Lesson.objects.create(
        course=lesson.course,
        section=lesson.section,
        slug="second",
        title="Second",
        position=2,
    )


def _asset(lesson, **overrides):
    from apps.media_assets.models import MediaAsset

    fields = {
        "lesson": lesson,
        "source_object_key": "masters/2026/abc123.mp4",
        "source_bytes": 1024,
        "provider": "fake",
    }
    return MediaAsset.objects.create(**{**fields, **overrides})


class TestOneAssetPerLesson:
    def test_a_second_asset_for_the_same_lesson_is_refused(self, lesson) -> None:
        """Two assets on one lesson is two answers to "what plays here", and
        the player would pick whichever the query returned first."""
        _asset(lesson)

        with pytest.raises(IntegrityError):
            _asset(lesson)

    def test_a_different_lesson_may_have_its_own(self, lesson, second_lesson) -> None:
        _asset(lesson)
        _asset(second_lesson)  # must not raise


class TestAPlaybackUrlCannotBeStored:
    """Invariant 7, moved from a rule people remember into one the database
    enforces.

    "Store `provider` + `provider_asset_id`. **Never store a playback URL.**"
    A stored URL means switching video provider is a data migration across
    every lesson plus a hunt through the codebase. The tempting mistake is not
    adding a `video_url` column — nobody would — it is quietly putting the URL
    in the id column because it happened to be what the provider returned.
    """

    def test_a_url_in_the_asset_id_is_refused(self, lesson) -> None:
        with pytest.raises(IntegrityError, match="provider_ids_are_not_urls"):
            _asset(lesson, provider_asset_id="https://stream.example.test/abc.m3u8")

    def test_a_url_in_the_playback_id_is_refused(self, lesson) -> None:
        with pytest.raises(IntegrityError, match="provider_ids_are_not_urls"):
            _asset(lesson, provider_playback_id="https://stream.example.test/abc.m3u8")

    def test_any_scheme_is_refused_not_just_https(self, lesson) -> None:
        """Matched on `://` rather than `http`, so a signed `s3://` or an
        `rtmp://` ingest URL is caught by the same rule."""
        with pytest.raises(IntegrityError, match="provider_ids_are_not_urls"):
            _asset(lesson, provider_playback_id="rtmp://ingest.example.test/live")

    def test_an_opaque_id_is_accepted(self, lesson) -> None:
        """The positive twin. A constraint that rejected everything would pass
        all three tests above and make the product unshippable."""
        asset = _asset(
            lesson,
            provider_asset_id="AbC123dEf456",
            provider_playback_id="xY9zQ1w2E3r4",
        )

        assert asset.provider_playback_id == "xY9zQ1w2E3r4"


class TestReadyMeansPlayable:
    def test_ready_without_a_playback_id_is_refused(self, lesson) -> None:
        """READY is what the playback-token endpoint checks before minting.
        An asset that claims to be ready with nothing to play is a 500 on the
        hottest path, at the moment somebody presses play."""
        with pytest.raises(IntegrityError, match="ready_assets_are_playable"):
            _asset(lesson, status="READY", provider_asset_id="abc123")

    def test_ready_without_an_asset_id_is_refused(self, lesson) -> None:
        with pytest.raises(IntegrityError, match="ready_assets_are_playable"):
            _asset(lesson, status="READY", provider_playback_id="xyz789")

    def test_ready_with_both_is_accepted(self, lesson) -> None:
        asset = _asset(
            lesson, status="READY", provider_asset_id="abc123", provider_playback_id="xyz789"
        )

        assert asset.status == "READY"

    def test_an_unfinished_asset_may_have_neither(self, lesson) -> None:
        """Everything before READY legitimately has no provider reference yet."""
        _asset(lesson, status="PENDING")


class TestFailureExplainsItself:
    def test_failed_without_a_message_is_refused(self, lesson) -> None:
        """The FAILED rows are the dead-letter queue (spec §4). One with no
        message is an item nobody can action — which is the silent failure
        §10 M5 names as the mistake for this milestone."""
        with pytest.raises(IntegrityError, match="failed_assets_explain_why"):
            _asset(lesson, status="FAILED", error_message="")

    def test_failed_with_a_message_is_accepted(self, lesson) -> None:
        asset = _asset(lesson, status="FAILED", error_message="Probe found no video stream.")

        assert asset.status == "FAILED"

    def test_a_healthy_asset_needs_no_message(self, lesson) -> None:
        _asset(lesson, status="UPLOADED")


class TestCountsAndSizes:
    def test_a_negative_retry_count_is_refused(self, lesson) -> None:
        with pytest.raises(IntegrityError):
            _asset(lesson, retry_count=-1)

    def test_a_zero_byte_source_is_refused(self, lesson) -> None:
        """An empty object is a failed upload the browser reported as success,
        and it would otherwise reach the transcoder as a real job."""
        with pytest.raises(IntegrityError, match="source_has_bytes"):
            _asset(lesson, source_bytes=0)


class TestWebhookEventIdempotency:
    """Invariant 8. This table *is* the idempotency mechanism."""

    def _event(self, **overrides):
        from apps.core.models import WebhookEvent

        fields = {
            "provider": "fake-video",
            "provider_event_id": "evt_123",
            "event_type": "video.asset.ready",
            "payload": {"id": "evt_123"},
        }
        return WebhookEvent.objects.create(**{**fields, **overrides})

    def test_the_same_event_twice_is_refused(self) -> None:
        """A provider retry must lose here rather than be caught by an `if`
        somewhere. Two workers can both check "have I seen this?", both see
        no, and both process — only a unique index makes one fail."""
        self._event()

        with pytest.raises(IntegrityError, match="webhook_event_unique_per_provider"):
            self._event()

    def test_two_providers_may_use_the_same_event_id(self) -> None:
        """Providers number their own events. Uniqueness is per provider, and
        a global unique would randomly reject one provider's event because
        another had used that id."""
        self._event(provider="fake-video")
        self._event(provider="fake-billing")

    def test_an_event_starts_unprocessed(self) -> None:
        """Insert first, process after (invariant 8). `processed_at` is what
        distinguishes "seen" from "done", and a replay arriving before the
        first one finishes must still be refused."""
        event = self._event()

        assert event.processed_at is None
