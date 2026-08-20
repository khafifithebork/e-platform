"""The video provider interface, and the fake that implements it.

Two properties are worth more than the rest.

The adapter returns **opaque ids, never URLs** — invariant 7 is what keeps
video migratable, and the database refuses ids containing "://", so an adapter
that returned a playback URL would fail at the constraint rather than quietly
making the provider unswappable.

And the fake's signing is **real**. A stub returning "token" would let every
T8 assertion pass while the token meant nothing, and a webhook verifier that
accepted anything would make T7's signature test vacuous — ADR-006's inert
control, in the one place where the control is the only thing between a
forged payload and our database.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from apps.media_assets.providers.fake_video import FakeVideoProvider, video_provider
from apps.media_assets.providers.video import (
    ProviderAssetStatus,
    VideoProvider,
    WebhookSignatureInvalid,
)

SOURCE = "https://storage.example.test/masters/abc/def.mp4?signature=x"


@pytest.fixture
def provider():
    return FakeVideoProvider()


class TestTheInterfaceIsSatisfied:
    def test_the_fake_implements_the_protocol(self, provider) -> None:
        """A protocol nothing is checked against is documentation. M8's
        adapter has to satisfy the same one."""
        assert isinstance(provider, VideoProvider)

    def test_the_factory_returns_a_provider(self) -> None:
        """Nothing else may import a concrete provider — ADR-012's claim that
        swapping is one file rests entirely on that."""
        assert isinstance(video_provider(), VideoProvider)

    def test_the_interface_has_the_three_documented_methods(self) -> None:
        """architecture.md §10 M5 names create_asset, get_playback_token and
        delete_asset as the things that keep video migratable."""
        for name in ("create_asset", "get_playback_token", "delete_asset"):
            assert callable(getattr(FakeVideoProvider, name)), name


class TestIdsAreOpaque:
    """Invariant 7, at the seam where a URL would enter the system."""

    def test_neither_id_looks_like_a_url(self, provider) -> None:
        asset = provider.create_asset(source_url=SOURCE)

        assert "://" not in asset.asset_id
        assert "://" not in asset.playback_id

    def test_the_ids_the_fake_returns_are_storable(self, db, provider) -> None:
        """The database refuses ids containing "://", so this proves the two
        agree — an adapter returning a URL fails here rather than in
        production."""
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Language, Lesson, Section
        from apps.media_assets.models import MediaAsset

        instructor = create_account(email="t@example.test", password="a-long-passphrase")
        language = Language.objects.create(code="es", name="Spanish", native_name="Esp")
        course = Course.objects.create(
            slug="c", title="C", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="S", position=1)
        lesson = Lesson.objects.create(
            course=course, section=section, slug="l", title="L", position=1
        )
        asset = provider.create_asset(source_url=SOURCE)

        stored = MediaAsset.objects.create(
            lesson=lesson,
            source_object_key="masters/x/y.mp4",
            source_bytes=1024,
            provider=asset.provider,
            provider_asset_id=asset.asset_id,
            provider_playback_id=asset.playback_id,
        )

        assert stored.provider_asset_id == asset.asset_id

    def test_two_assets_get_different_ids(self, provider) -> None:
        first = provider.create_asset(source_url=SOURCE)
        second = provider.create_asset(source_url=SOURCE)

        assert first.asset_id != second.asset_id
        assert first.playback_id != second.playback_id


class TestIngest:
    def test_a_new_asset_is_processing_not_ready(self, provider) -> None:
        """A real provider transcodes asynchronously and reports later. A fake
        returning READY would let the pipeline skip the state the webhook
        handler exists to deliver, so T7 would test a path production never
        takes."""
        assert provider.create_asset(source_url=SOURCE).status == ProviderAssetStatus.PROCESSING

    def test_an_object_key_is_refused_where_a_url_belongs(self, provider) -> None:
        """The provider fetches this itself, so a key instead of a URL means
        the asset fails minutes later, somewhere else."""
        with pytest.raises(ValueError, match="must be a URL"):
            provider.create_asset(source_url="masters/abc/def.mp4")


class TestPlaybackTokens:
    def test_a_fresh_token_authorises_its_own_asset(self, provider) -> None:
        token = provider.get_playback_token(playback_id="fakeplay_abc", ttl_seconds=60)

        assert provider.verify_playback_token(token=token.token, playback_id="fakeplay_abc")

    def test_a_token_does_not_open_a_different_asset(self, provider) -> None:
        """The property that matters. A token not scoped to one asset means
        entitlement is checked once and bypassed everywhere after — one paid
        lesson becomes the whole catalogue."""
        token = provider.get_playback_token(playback_id="fakeplay_abc", ttl_seconds=60)

        assert not provider.verify_playback_token(
            token=token.token, playback_id="fakeplay_somebody_else"
        )

    def test_an_expired_token_stops_working(self, provider) -> None:
        """§7 requires a short TTL: a token that never expires is a permanent
        share link for paid content."""
        token = provider.get_playback_token(playback_id="fakeplay_abc", ttl_seconds=-1)

        assert not provider.verify_playback_token(token=token.token, playback_id="fakeplay_abc")

    def test_the_expiry_is_reported_accurately(self, provider) -> None:
        """The caller passes this to the client so a player can refresh before
        it lapses; a wrong value means playback dies mid-lesson."""
        token = provider.get_playback_token(playback_id="fakeplay_abc", ttl_seconds=300)

        assert timedelta(seconds=290) < token.expires_at - datetime.now(UTC)

    def test_a_tampered_token_is_refused(self, provider) -> None:
        """Signed, not merely encoded. Without the signature a client could
        rewrite the expiry it was given."""
        token = provider.get_playback_token(playback_id="fakeplay_abc", ttl_seconds=60)
        tampered = token.token[:-4] + "AAAA"

        assert not provider.verify_playback_token(token=tampered, playback_id="fakeplay_abc")

    def test_rubbish_is_refused_rather_than_raising(self, provider) -> None:
        """A malformed token is a client error, not a 500."""
        assert not provider.verify_playback_token(token="not-a-token", playback_id="x")

    def test_the_token_is_not_a_url(self, provider) -> None:
        """Abuse case 11. We hand out a handle and a token; the player
        composes a URL, so changing provider changes nothing we ever sent."""
        token = provider.get_playback_token(playback_id="fakeplay_abc", ttl_seconds=60)

        assert "://" not in token.token


class TestWebhookSignatures:
    """Invariant 8 puts verification first, before the event is recorded."""

    def test_a_genuine_signature_is_accepted(self, provider) -> None:
        """The positive case is what makes the negative ones mean something: a
        verifier that rejected everything would pass every test below."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")

        provider.verify_webhook(payload=payload, signature=signature)

    def test_a_forged_signature_is_refused(self, provider) -> None:
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc")

        with pytest.raises(WebhookSignatureInvalid):
            provider.verify_webhook(payload=payload, signature="0" * 64)

    def test_an_altered_payload_is_refused(self, provider) -> None:
        """The attack the signature exists for: a real event, edited to name a
        different asset."""
        payload, signature = provider.build_webhook(asset_id="fakeasset_abc")
        altered = json.loads(payload)
        altered["asset_id"] = "fakeasset_somebody_else"

        with pytest.raises(WebhookSignatureInvalid):
            provider.verify_webhook(payload=json.dumps(altered).encode(), signature=signature)

    def test_an_empty_signature_is_refused(self, provider) -> None:
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc")

        with pytest.raises(WebhookSignatureInvalid):
            provider.verify_webhook(payload=payload, signature="")


class TestParsingWebhooks:
    def test_a_payload_becomes_our_vocabulary(self, provider) -> None:
        payload, _ = provider.build_webhook(
            asset_id="fakeasset_abc", event_id="fakeevt_1", duration_seconds=91
        )

        event = provider.parse_webhook(payload=payload)

        assert event.event_id == "fakeevt_1"
        assert event.asset_id == "fakeasset_abc"
        assert event.status == ProviderAssetStatus.READY
        assert event.duration_seconds == 91

    def test_the_same_payload_keeps_the_same_event_id(self, provider) -> None:
        """What invariant 8's unique constraint is applied to. An id derived
        rather than taken from the provider would differ between two
        deliveries of the same event, and the idempotency table would catch
        nothing."""
        payload, _ = provider.build_webhook(asset_id="fakeasset_abc", event_id="fakeevt_1")

        first = provider.parse_webhook(payload=payload)
        second = provider.parse_webhook(payload=payload)

        assert first.event_id == second.event_id

    def test_a_failure_event_carries_the_errored_status(self, provider) -> None:
        payload, _ = provider.build_webhook(
            asset_id="fakeasset_abc", status=ProviderAssetStatus.ERRORED
        )

        assert provider.parse_webhook(payload=payload).status == ProviderAssetStatus.ERRORED
