"""Processing, retries, and the dead-letter queue.

§10 M5 names "no dead-letter queue, so failures vanish silently" as the
mistake for this milestone, so the failure paths get more attention here than
the happy one.

Two properties are load-bearing and easy to get wrong in ways nothing notices:

**A retry must not create a second provider asset.** A task that timed out may
have succeeded on the provider's side, and running it again would pay for a
second transcode and leave a playback id nothing references.

**A dead-lettered asset must be retryable without re-uploading.** The master is
ours — that is the whole reason for storing it — so a provider outage should
cost a click rather than asking an instructor to send two gigabytes again.

The task is called synchronously with `.apply()` rather than through a broker:
these tests are about what the task *does*, and a real worker would only add a
queue between the assertion and the behaviour.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture
def asset(db):
    """An uploaded master waiting to be processed."""
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, Language, Lesson, Section

    instructor = create_account(email="teacher@example.test", password=PASSWORD)
    instructor.role = Role.INSTRUCTOR
    instructor.save(update_fields=["role"])

    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    return MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        status=MediaAssetStatus.UPLOADED,
    )


def _run(asset_id) -> str:
    from apps.media_assets.tasks import process_media_asset

    return process_media_asset.apply(args=[str(asset_id)]).get()


class TestTheHappyPath:
    def test_the_asset_is_handed_to_the_provider(self, asset) -> None:
        assert _run(asset.pk) == "handed-to-provider"

        asset.refresh_from_db()
        assert asset.provider == "fake"
        assert asset.provider_asset_id
        assert asset.provider_playback_id

    def test_it_becomes_transcoding_not_ready(self, asset) -> None:
        """READY here would mint playback tokens for something the provider
        has not finished transcoding. Completion arrives by webhook (T7)."""
        _run(asset.pk)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING

    def test_the_provider_is_given_a_url_it_can_fetch(self, asset) -> None:
        """Invariant 6 in the other direction: the provider pulls the master
        itself, so the bytes never pass through Django on the way out either."""
        from apps.media_assets.providers.fake_video import FakeVideoProvider

        seen = {}
        original = FakeVideoProvider.create_asset

        def record(self, *, source_url):
            seen["url"] = source_url
            return original(self, source_url=source_url)

        with patch.object(FakeVideoProvider, "create_asset", record):
            _run(asset.pk)

        assert seen["url"].startswith("http")
        assert "def.mp4" in seen["url"]

    def test_no_playback_url_is_stored(self, asset) -> None:
        """Invariant 7. The database refuses "://" in either id column, so
        this passing means the adapter and the constraint agree."""
        _run(asset.pk)

        asset.refresh_from_db()
        assert "://" not in asset.provider_asset_id
        assert "://" not in asset.provider_playback_id


class TestItDoesNotActTwice:
    def test_running_again_does_not_create_a_second_provider_asset(self, asset) -> None:
        """The retry-after-timeout case. The task may have succeeded on the
        provider's side and never heard back, so a second run would pay for a
        second transcode and orphan the first."""
        _run(asset.pk)
        asset.refresh_from_db()
        first_id = asset.provider_asset_id

        assert _run(asset.pk) == "already-processed"

        asset.refresh_from_db()
        assert asset.provider_asset_id == first_id

    def test_an_asset_that_is_not_uploaded_is_left_alone(self, asset) -> None:
        """A replacement upload put it back to PENDING while this task sat in
        the queue. Acting now would overwrite that with a stale view."""
        MediaAsset.objects.filter(pk=asset.pk).update(status=MediaAssetStatus.PENDING)

        assert _run(asset.pk) == "not-uploaded:PENDING"

    def test_a_deleted_asset_is_not_an_error(self, asset) -> None:
        """The lesson was deleted while the task was queued, which is
        ordinary and must not fill the log with failures."""
        asset_id = asset.pk
        asset.delete()

        assert _run(asset_id) == "gone"


class TestTheDeadLetterQueue:
    def test_a_persistent_failure_lands_in_the_queue(self, asset, settings) -> None:
        """The deliverable §10 M5 asks for. A traceback in a worker log is not
        a queue: this row is queryable, countable, and carries what happened."""
        settings.MEDIA_PROCESSING_MAX_RETRIES = 0
        from apps.media_assets.providers.fake_video import FakeVideoProvider

        with patch.object(
            FakeVideoProvider, "create_asset", side_effect=RuntimeError("provider is down")
        ):
            assert _run(asset.pk) == "dead-lettered"

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.FAILED
        assert "provider is down" in asset.error_message

    def test_the_failure_record_survives(self, asset, settings) -> None:
        """The T4 bug, in the place it would recur. A failure written inside a
        transaction that then unwinds leaves the queue permanently empty while
        looking like it works."""
        settings.MEDIA_PROCESSING_MAX_RETRIES = 0
        from apps.media_assets.providers.fake_video import FakeVideoProvider

        with patch.object(FakeVideoProvider, "create_asset", side_effect=RuntimeError("boom")):
            _run(asset.pk)

        assert MediaAsset.objects.filter(status=MediaAssetStatus.FAILED).count() == 1

    def test_a_provider_rejection_does_not_burn_the_retry_budget(self, asset) -> None:
        """Retrying an unchanged file against an unchanged provider produces
        the same answer, so this goes straight to the queue."""
        from apps.media_assets.providers.fake_video import FakeVideoProvider
        from apps.media_assets.providers.video import ProviderAsset, ProviderAssetStatus

        rejected = ProviderAsset(
            provider="fake",
            asset_id="fakeasset_x",
            playback_id="fakeplay_x",
            status=ProviderAssetStatus.ERRORED,
        )
        with patch.object(FakeVideoProvider, "create_asset", return_value=rejected):
            assert _run(asset.pk) == "provider-rejected"

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.FAILED
        assert asset.retry_count == 0

    def test_a_transient_failure_recovers(self, asset, settings) -> None:
        """The branch the tests above skip by setting the budget to zero, and
        the reason retries exist at all: a thirty-second provider outage must
        not permanently fail every asset uploaded during it.

        Asserted through the outcome rather than by watching for a Retry.
        Celery's eager mode runs retries *inline*, so an exception never
        surfaces — a test looking for one reports "did not raise" against code
        that is retrying correctly.
        """
        from apps.media_assets.providers.fake_video import FakeVideoProvider
        from apps.media_assets.providers.video import ProviderAsset, ProviderAssetStatus

        settings.MEDIA_PROCESSING_MAX_RETRIES = 3
        succeeded = ProviderAsset(
            provider="fake",
            asset_id="fakeasset_recovered",
            playback_id="fakeplay_recovered",
            status=ProviderAssetStatus.PROCESSING,
        )

        with patch.object(
            FakeVideoProvider,
            "create_asset",
            side_effect=[RuntimeError("briefly down"), succeeded],
        ):
            _run(asset.pk)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING
        assert asset.provider_asset_id == "fakeasset_recovered"

    def test_the_backoff_grows(self) -> None:
        """Exponential, and asserted on the schedule itself because eager mode
        hides it. A fixed delay would satisfy "there is a retry" while still
        hammering an unavailable provider."""
        from apps.media_assets.tasks import retry_countdown

        delays = [retry_countdown(attempt) for attempt in (1, 2, 3)]

        assert delays == [20, 40, 80]
        assert delays == sorted(delays)

    def test_the_queue_is_queryable(self, asset, settings) -> None:
        """What makes it a queue rather than a log line: an operator can ask
        what is broken, and an alert can count it."""
        settings.MEDIA_PROCESSING_MAX_RETRIES = 0
        from apps.media_assets.providers.fake_video import FakeVideoProvider

        with patch.object(FakeVideoProvider, "create_asset", side_effect=RuntimeError("x")):
            _run(asset.pk)

        assert MediaAsset.objects.filter(status=MediaAssetStatus.FAILED).exists()


class TestRetryingByHand:
    def test_a_failed_asset_can_be_retried_without_re_uploading(self, asset) -> None:
        """The whole reason the master is ours (invariant 7). A provider
        outage should cost a click, not two gigabytes of an instructor's
        time."""
        from apps.media_assets.services import retry_processing

        MediaAsset.objects.filter(pk=asset.pk).update(
            status=MediaAssetStatus.FAILED, error_message="provider was down", retry_count=3
        )
        asset.refresh_from_db()
        key_before = asset.source_object_key

        retry_processing(asset=asset)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.UPLOADED
        assert asset.error_message == ""
        assert asset.retry_count == 0
        # Same master: nothing was re-uploaded.
        assert asset.source_object_key == key_before

    def test_retrying_queues_the_work_again(
        self, asset, django_capture_on_commit_callbacks
    ) -> None:
        """A retry that resets the row but queues nothing leaves the asset
        stuck in UPLOADED forever, looking healthy."""
        from apps.media_assets.services import retry_processing

        MediaAsset.objects.filter(pk=asset.pk).update(
            status=MediaAssetStatus.FAILED, error_message="down"
        )
        asset.refresh_from_db()

        with (
            patch("apps.media_assets.tasks.process_media_asset.delay") as queued,
            django_capture_on_commit_callbacks(execute=True),
        ):
            retry_processing(asset=asset)

        assert queued.called

    def test_a_retried_asset_processes_successfully(self, asset) -> None:
        from apps.media_assets.services import retry_processing

        MediaAsset.objects.filter(pk=asset.pk).update(
            status=MediaAssetStatus.FAILED, error_message="down"
        )
        asset.refresh_from_db()

        retry_processing(asset=asset)
        _run(asset.pk)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING

    def test_only_a_failed_asset_may_be_retried(self, asset) -> None:
        """Retrying something mid-flight races the task already running it."""
        from apps.media_assets.services import UploadNotAllowed, retry_processing

        with pytest.raises(UploadNotAllowed):
            retry_processing(asset=asset)


class TestEnqueueing:
    def test_completing_an_upload_queues_the_work(
        self, asset, django_capture_on_commit_callbacks
    ) -> None:
        """The link between T4 and this task. Without it an upload verifies
        and then sits there, and nothing says so.

        The enqueue is a `transaction.on_commit` callback, which **never fires
        under pytest-django** because the test transaction is rolled back
        rather than committed — the same invisibility as M3's deferred
        constraints. Without `django_capture_on_commit_callbacks` this test
        would fail against correct code, and a version that asserted the
        callback was merely *registered* would pass against code that queued
        nothing.
        """
        from apps.media_assets.providers.storage import StoredObject

        MediaAsset.objects.filter(pk=asset.pk).update(status=MediaAssetStatus.PENDING)
        asset.refresh_from_db()

        class _Store:
            def head(self, *, object_key):
                return StoredObject(
                    key=object_key, size_bytes=2048, content_type="video/mp4", etag="abc"
                )

            def read_prefix(self, *, object_key, length=16):
                return b"\x00\x00\x00\x20ftypisom"

            def delete(self, *, object_key):
                pass

        from apps.media_assets.services import complete_upload

        with (
            patch("apps.media_assets.tasks.process_media_asset.delay") as queued,
            django_capture_on_commit_callbacks(execute=True),
        ):
            complete_upload(asset=asset, by=asset.lesson.course.instructor, storage=_Store())

        assert queued.called, "a verified upload must be queued for processing"
        assert queued.call_args.args == (str(asset.pk),)
