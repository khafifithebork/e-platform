"""Processing status and the retry path — the visible half of M5.

The milestone's deliverable is "instructor uploads a video and it becomes
playable, gated by entitlement, with **visible processing status and a real
failure path**". Without these two endpoints the pipeline is a black box: an
upload either works or nothing ever says otherwise, which is how a failed
asset gets discovered on publication day.

The retry path is where owning the master pays off (invariant 7). A provider
outage should cost a click, not two gigabytes of an instructor's time — and
the test asserts the object key is unchanged, because "retry" that silently
required a re-upload would satisfy a weaker assertion.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus

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


def _user(email: str, role: str = Role.INSTRUCTOR):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test")


@pytest.fixture
def asset(db, instructor):
    from apps.catalog.models import Course, Language, Lesson, Section

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
        status=MediaAssetStatus.TRANSCODING,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
    )


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _detail(asset) -> str:
    return f"/api/v1/media-assets/{asset.id}/"


def _retry(asset) -> str:
    return f"/api/v1/media-assets/{asset.id}/retry/"


def _fail(asset, message: str = "provider was down") -> None:
    MediaAsset.objects.filter(pk=asset.pk).update(
        status=MediaAssetStatus.FAILED, error_message=message, retry_count=3
    )


class TestSeeingWhatHappened:
    def test_the_owner_sees_the_status(self, client, asset) -> None:
        _sign_in(client, "teacher@example.test")

        body = client.get(_detail(asset)).json()

        assert body["status"] == "TRANSCODING"

    def test_a_failure_says_why_and_how_many_times(self, client, asset) -> None:
        """The three fields the dead-letter queue is read from, shown to the
        person most able to act on them."""
        _fail(asset, "The provider rejected the file.")
        _sign_in(client, "teacher@example.test")

        body = client.get(_detail(asset)).json()

        assert body["status"] == "FAILED"
        assert body["error_message"] == "The provider rejected the file."
        assert body["retry_count"] == 3

    def test_another_instructor_gets_a_404(self, client, asset) -> None:
        """Not 403 (§6.3). The asset is addressed by its own id, so ownership
        is checked in the view rather than by a queryset filter — which is
        exactly the case architecture.md §4.4 calls the commonest IDOR."""
        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert client.get(_detail(asset)).status_code == 404

    def test_a_student_gets_a_404(self, client, asset) -> None:
        _user("student@example.test", Role.STUDENT)
        _sign_in(client, "student@example.test")

        assert client.get(_detail(asset)).status_code == 404

    def test_anonymous_is_refused(self, client, asset) -> None:
        assert client.get(_detail(asset)).status_code in (401, 403)

    def test_an_admin_may_look(self, client, asset) -> None:
        _user("boss@example.test", Role.ADMIN)
        _sign_in(client, "boss@example.test")

        assert client.get(_detail(asset)).status_code == 200

    def test_no_provider_handles_are_exposed(self, client, asset) -> None:
        """Abuse case 10. The playback id belongs in a minted token and
        nowhere else — not even on the uploader's own status screen."""
        _sign_in(client, "teacher@example.test")

        response = client.get(_detail(asset))

        assert b"fakeplay_abc" not in response.content
        assert b"masters/abc" not in response.content


class TestRetrying:
    def test_a_failed_asset_can_be_retried(self, client, asset) -> None:
        _fail(asset)
        _sign_in(client, "teacher@example.test")

        response = client.post(_retry(asset))

        assert response.status_code == 200
        assert response.json()["status"] == "UPLOADED"

    def test_retrying_does_not_require_re_uploading(self, client, asset) -> None:
        """The practical argument for storing the master ourselves. A "retry"
        that silently needed a fresh upload would satisfy the test above."""
        _fail(asset)
        key_before = asset.source_object_key
        _sign_in(client, "teacher@example.test")

        client.post(_retry(asset))

        asset.refresh_from_db()
        assert asset.source_object_key == key_before

    def test_retrying_clears_the_stale_failure(self, client, asset) -> None:
        """A row still carrying the last error describes an attempt that is no
        longer the current one, and the FAILED rows are the queue."""
        _fail(asset)
        _sign_in(client, "teacher@example.test")

        client.post(_retry(asset))

        asset.refresh_from_db()
        assert asset.error_message == ""
        assert asset.retry_count == 0

    def test_retrying_queues_the_work(
        self, client, asset, django_capture_on_commit_callbacks
    ) -> None:
        """A retry that resets the row but queues nothing leaves the asset in
        UPLOADED forever, looking healthy and doing nothing."""
        from unittest.mock import patch

        _fail(asset)
        _sign_in(client, "teacher@example.test")

        with (
            patch("apps.media_assets.tasks.process_media_asset.delay") as queued,
            django_capture_on_commit_callbacks(execute=True),
        ):
            client.post(_retry(asset))

        assert queued.called

    def test_retrying_something_mid_flight_is_a_conflict(self, client, asset) -> None:
        """TRANSCODING means a task is already on it; a second would race."""
        _sign_in(client, "teacher@example.test")

        assert client.post(_retry(asset)).status_code == 409

    def test_another_instructor_cannot_retry(self, client, asset) -> None:
        _fail(asset)
        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert client.post(_retry(asset)).status_code == 404
        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.FAILED


class TestTheDeadLetterQueueIsReadable:
    """A queue nobody can look at is the failure §10 M5 names, with extra
    steps. Reached through the test-only urlconf, since admin stays unrouted
    until M10 (ADR-008 §5)."""

    @pytest.fixture(autouse=True)
    def _admin_is_routed(self, settings):
        settings.ROOT_URLCONF = "tests.urls_with_admin"

    @pytest.fixture
    def admin_user(self, db):
        user = _user("admin@example.test", Role.ADMIN)
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
        return user

    def test_failed_assets_can_be_listed(self, client, asset, admin_user) -> None:
        _fail(asset, "provider exploded")
        _sign_in(client, "admin@example.test")

        page = client.get("/admin/media_assets/mediaasset/?status__exact=FAILED").content

        assert b"FAILED" in page

    def test_status_cannot_be_edited_by_hand(self, client, asset, admin_user) -> None:
        """A writable status could mark an asset READY that the provider never
        transcoded — minting playback tokens for something nobody can play."""
        _sign_in(client, "admin@example.test")

        client.post(
            f"/admin/media_assets/mediaasset/{asset.pk}/change/",
            {"status": "READY", "retry_count": 0},
        )

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING

    def test_an_asset_cannot_be_deleted(self, client, asset, admin_user) -> None:
        """Deleting the row orphans the object in storage: we keep paying for
        a master nothing references."""
        _sign_in(client, "admin@example.test")

        response = client.post(f"/admin/media_assets/mediaasset/{asset.pk}/delete/")

        assert response.status_code == 403
        assert MediaAsset.objects.filter(pk=asset.pk).exists()

    def test_the_admin_action_requeues_a_failed_asset(self, client, asset, admin_user) -> None:
        _fail(asset)
        _sign_in(client, "admin@example.test")

        client.post(
            "/admin/media_assets/mediaasset/",
            {"action": "retry_failed", "_selected_action": [str(asset.pk)]},
            follow=True,
        )

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.UPLOADED

    def test_the_action_reports_an_asset_it_cannot_retry(self, client, asset, admin_user) -> None:
        """A selection routinely mixes states; one that cannot move must be
        reported rather than silently skipped."""
        _sign_in(client, "admin@example.test")

        response = client.post(
            "/admin/media_assets/mediaasset/",
            {"action": "retry_failed", "_selected_action": [str(asset.pk)]},
            follow=True,
        )

        assert b"not failed" in response.content

    def test_a_webhook_event_cannot_be_deleted(self, client, admin_user) -> None:
        """Deleting a row from the idempotency table lets a replayed event be
        processed a second time — the exact thing the unique constraint
        prevents. It looks like tidying up."""
        from apps.core.models import WebhookEvent

        event = WebhookEvent.objects.create(
            provider="fake",
            provider_event_id="fakeevt_1",
            event_type="video.asset.ready",
            payload={},
        )
        _sign_in(client, "admin@example.test")

        response = client.post(f"/admin/core/webhookevent/{event.pk}/delete/")

        assert response.status_code == 403
        assert WebhookEvent.objects.filter(pk=event.pk).exists()
