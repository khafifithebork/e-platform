"""The webhook receiver: invariant 8, provoked.

Abuse cases 7, 8 and 9. The four steps have to happen *in order*, and each
wrong order is a real failure rather than untidiness:

- Recording before verifying lets anyone fill the idempotency table with ids
  the real provider is then refused for — a denial of service made of our own
  guard.
- Acting before recording means a replay acts twice.
- Answering anything but 200 to a replay guarantees more replays, because a
  provider that receives an error assumes we missed the event.

The signature tests are only worth something because the fake can produce a
**valid** signature too: a handler that rejected everything would satisfy
every negative case here.
"""

from __future__ import annotations

import json

import pytest

from apps.accounts.models import Role
from apps.core.models import WebhookEvent
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.media_assets.providers.fake_video import FakeVideoProvider
from apps.media_assets.providers.video import ProviderAssetStatus

WEBHOOK = "/api/v1/webhooks/video/"
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


@pytest.fixture
def provider():
    return FakeVideoProvider()


@pytest.fixture
def asset(db):
    """An asset already handed to the provider, waiting to be told it is ready."""
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
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.TRANSCODING,
    )


def _deliver(client, payload: bytes, signature: str):
    return client.post(
        WEBHOOK,
        data=payload,
        content_type="application/json",
        HTTP_X_WEBHOOK_SIGNATURE=signature,
    )


def _run_queued(callbacks) -> None:
    """Execute what the handler queued, as a worker would."""
    from apps.media_assets.tasks import apply_media_webhook

    for record in WebhookEvent.objects.filter(processed_at__isnull=True):
        apply_media_webhook.apply(args=[str(record.pk)]).get()


class TestTheSignatureIsCheckedFirst:
    """Abuse case 8."""

    def test_a_forged_signature_is_refused(self, client, provider, asset) -> None:
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc")

        response = _deliver(client, payload, "0" * 64)

        assert response.status_code == 401

    def test_a_forged_signature_records_nothing(self, client, provider, asset) -> None:
        """The order that matters. Recording first would let anyone fill the
        idempotency table with ids the real provider is then refused for."""
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc", event_id="fakeevt_1")

        _deliver(client, payload, "0" * 64)

        assert not WebhookEvent.objects.exists()

    def test_a_forged_signature_changes_no_media(self, client, provider, asset) -> None:
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc")

        _deliver(client, payload, "0" * 64)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING

    def test_a_missing_signature_is_refused(self, client, provider, asset) -> None:
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc")

        assert (
            client.post(WEBHOOK, data=payload, content_type="application/json").status_code == 401
        )

    def test_an_altered_payload_is_refused(self, client, provider, asset) -> None:
        """A real event, edited to name a different asset — the attack the
        signature exists for."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")
        altered = json.loads(payload)
        altered["asset_id"] = "fakeasset_somebody_else"

        response = _deliver(client, json.dumps(altered).encode(), signature)

        assert response.status_code == 401

    def test_a_genuine_signature_is_accepted(self, client, provider, asset) -> None:
        """The positive twin, and the reason the four tests above mean
        something: a handler that refused everything would pass all of them."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")

        assert _deliver(client, payload, signature).status_code == 200


class TestIdempotency:
    """Abuse case 7. The unique constraint is the mechanism, not an `if`."""

    def test_the_event_is_recorded_before_anything_is_done(self, client, provider, asset) -> None:
        """200 is returned with the media untouched. The provider is told we
        have the event, not that we have acted on it."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")

        _deliver(client, payload, signature)

        assert WebhookEvent.objects.count() == 1
        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING

    def test_a_replay_returns_200_without_a_second_record(self, client, provider, asset) -> None:
        """Anything but 200 to a replay guarantees more replays: a provider
        that receives an error assumes we missed the event."""
        payload, signature = provider.build_webhook(
            asset_id="fakeasset_abc", event_id="fakeevt_same"
        )

        first = _deliver(client, payload, signature)
        second = _deliver(client, payload, signature)

        assert (first.status_code, second.status_code) == (200, 200)
        assert WebhookEvent.objects.count() == 1

    def test_a_replay_does_not_apply_the_event_twice(
        self, client, provider, asset, django_capture_on_commit_callbacks
    ) -> None:
        """The consequence idempotency exists to prevent. Here it is only a
        duplicate transcode; in M8, on the same table, it is a subscription
        extended twice."""
        payload, signature = provider.build_webhook(
            asset_id="fakeasset_abc", event_id="fakeevt_same", duration_seconds=90
        )

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            _deliver(client, payload, signature)
            _deliver(client, payload, signature)

        # One enqueue for two deliveries: the second never got past the insert.
        assert len(callbacks) == 1

    def test_two_different_events_are_both_recorded(self, client, provider, asset) -> None:
        """The positive twin. A handler treating everything as a duplicate
        would satisfy every test above and process nothing."""
        first_payload, first_signature = provider.build_webhook(
            asset_id="fakeasset_abc", event_id="fakeevt_1"
        )
        second_payload, second_signature = provider.build_webhook(
            asset_id="fakeasset_abc", event_id="fakeevt_2"
        )

        _deliver(client, first_payload, first_signature)
        _deliver(client, second_payload, second_signature)

        assert WebhookEvent.objects.count() == 2


class TestApplyingTheEvent:
    def test_a_ready_event_makes_the_asset_playable(
        self, client, provider, asset, django_capture_on_commit_callbacks
    ) -> None:
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc", duration_seconds=181)

        with django_capture_on_commit_callbacks(execute=False):
            _deliver(client, payload, signature)
        _run_queued(None)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.READY
        assert asset.duration_seconds == 181

    def test_an_errored_event_lands_in_the_dead_letter_queue(
        self, client, provider, asset, django_capture_on_commit_callbacks
    ) -> None:
        """A provider that fails after accepting the file must not leave the
        asset stuck in TRANSCODING forever, looking like it is still working."""
        payload, signature = provider.build_webhook(
            asset_id="fakeasset_abc", status=ProviderAssetStatus.ERRORED
        )

        with django_capture_on_commit_callbacks(execute=False):
            _deliver(client, payload, signature)
        _run_queued(None)

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.FAILED
        assert asset.error_message

    def test_the_event_is_marked_processed(self, client, provider, asset) -> None:
        """What separates "seen" from "done". Left unset, every applied event
        sits in the unprocessed queue looking urgent."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")
        _deliver(client, payload, signature)

        _run_queued(None)

        assert WebhookEvent.objects.get().processed_at is not None

    def test_applying_twice_is_a_no_op(self, client, provider, asset) -> None:
        """A task redelivered after a worker died re-applies the same state,
        which is why processed_at is set at the end rather than used as a
        skip-if-set guard."""
        from apps.media_assets.tasks import apply_media_webhook

        payload, signature = provider.build_webhook(asset_id="fakeasset_abc", duration_seconds=181)
        _deliver(client, payload, signature)
        record = WebhookEvent.objects.get()

        assert apply_media_webhook.apply(args=[str(record.pk)]).get() == "ready"
        assert apply_media_webhook.apply(args=[str(record.pk)]).get() == "ready"

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.READY
        assert asset.duration_seconds == 181


class TestUnknownAssets:
    """Abuse case 9."""

    def test_an_event_for_an_unknown_asset_creates_nothing(self, client, provider, asset) -> None:
        """Either a stale event for something deleted, or an event for
        somebody else's account. Neither is a reason to invent a row."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_nobody")
        _deliver(client, payload, signature)

        _run_queued(None)

        assert MediaAsset.objects.count() == 1
        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING

    def test_it_is_still_marked_processed(self, client, provider, asset) -> None:
        """Otherwise it sits in the unprocessed queue forever, and the queue
        stops meaning "things that went wrong"."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_nobody")
        _deliver(client, payload, signature)

        _run_queued(None)

        assert WebhookEvent.objects.get().processed_at is not None


class TestTheHandlerHoldsNoBusinessLogic:
    def test_a_malformed_payload_is_a_400_not_a_500(self, client, provider) -> None:
        """A payload we cannot read is not worth a retry — the provider would
        send the same bytes again — so it must not be a 5xx."""
        payload = json.dumps({"nonsense": True}).encode()
        signature = provider.sign_webhook(payload=payload)

        assert _deliver(client, payload, signature).status_code == 400

    def test_no_authentication_is_required(self, client, provider, asset) -> None:
        """The provider has no session and no CSRF token. The signature is the
        authentication, which is why it is checked first."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")

        assert _deliver(client, payload, signature).status_code == 200

    def test_the_handler_returns_before_the_media_changes(self, client, provider, asset) -> None:
        """Invariant 8's fourth step. Work done in the request is work that can
        turn a slow database into a provider retry storm."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")

        assert _deliver(client, payload, signature).status_code == 200

        asset.refresh_from_db()
        assert asset.status == MediaAssetStatus.TRANSCODING
