"""A video provider that transcodes nothing.

Exists so the pipeline is built and tested before a video provider is chosen
and paid for (ADR-012 §1). M4 did the same with billing, and the result was
that M8 becomes a swap rather than a rewrite.

It is a **real adapter**, not a mock. CLAUDE.md §6 forbids mocking our own
service layer and asserting it was called. Tests drive this through the same
interface M8's Mux adapter will implement and assert on what the database ends
up believing.

Two things are implemented properly rather than stubbed, because the tests
that matter would otherwise prove nothing:

**Playback tokens are really signed and really expire.** A stub returning
``"token"`` would let every T8 assertion pass while the token was meaningless,
and the one property worth having — that a token stops working — would be
untested until a real provider arrived.

**Webhook signatures are really verified**, with a constant-time comparison.
Invariant 8 puts verification first, and a fake that accepted anything would
make T7's signature test vacuous — which is ADR-006's inert control exactly.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from django.conf import settings

from apps.media_assets.providers.video import (
    PlaybackToken,
    ProviderAsset,
    ProviderAssetStatus,
    ProviderWebhookEvent,
    WebhookSignatureInvalid,
)


def _b64(raw: bytes) -> str:
    """URL-safe base64 with padding stripped, so a token is one path-safe word."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(encoded: str) -> bytes:
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


def _secret() -> bytes:
    """The key this fake signs with.

    Derived from ``SECRET_KEY`` rather than read from its own setting. A real
    provider supplies its own signing secret and M8 will add one; requiring a
    variable now, for a provider that does not exist, would be a required
    setting every environment has to carry for nothing.

    Domain-separated so a fake playback token can never be mistaken for, or
    replayed as, anything else signed with the same key.
    """
    return hashlib.sha256(f"fake-video:{settings.SECRET_KEY}".encode()).digest()


class FakeVideoProvider:
    """Deterministic, free, and holds no state.

    Each call computes its answer from the arguments and the clock. A real
    provider is the authority on its own assets; this one has no authority to
    model, so it invents the minimum that lets our side be exercised.
    """

    name = "fake"

    # --- ingest ---------------------------------------------------------

    def create_asset(self, *, source_url: str) -> ProviderAsset:
        """Accept a master and report it as processing.

        PROCESSING rather than READY, deliberately: a real provider transcodes
        asynchronously and tells us later by webhook, so a fake that returned
        READY immediately would let the pipeline skip the state the webhook
        handler exists to deliver — and T7 would be testing a path production
        never takes.
        """
        if "://" not in source_url:
            # Not fussy validation: the provider fetches this itself, so a
            # value that is not a URL means we handed it an object key by
            # mistake and the asset would fail minutes later, elsewhere.
            raise ValueError("source_url must be a URL the provider can fetch")

        return ProviderAsset(
            provider=self.name,
            # Opaque, and containing no "://" — the database refuses ids that
            # look like URLs (invariant 7).
            asset_id=f"fakeasset_{secrets.token_urlsafe(12)}",
            playback_id=f"fakeplay_{secrets.token_urlsafe(12)}",
            status=ProviderAssetStatus.PROCESSING,
            raw={"source": "accepted"},
        )

    def delete_asset(self, *, asset_id: str) -> None:
        """Nothing to delete; the fake stores nothing.

        Present because the interface requires it and because the *call* is
        what matters: T9 asserts that discarding an asset asks the provider to
        drop its copy, and a missing method would make that untestable.
        """
        return None

    # --- playback -------------------------------------------------------

    def get_playback_token(self, *, playback_id: str, ttl_seconds: int) -> PlaybackToken:
        """Sign permission to play one asset until a moment.

        Scoped to the playback id: a token minted for one lesson must not play
        another, or entitlement is checked once and bypassed everywhere after.
        """
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        expiry = int(expires_at.timestamp())
        payload = f"{playback_id}:{expiry}".encode()
        signature = hmac.new(_secret(), payload, hashlib.sha256).digest()

        # Each half is base64-encoded *before* joining, and the separator is a
        # character the base64url alphabet does not contain. Joining the raw
        # bytes and splitting on b"." was wrong in a way that only showed up
        # about one run in eight: an HMAC digest is 32 arbitrary bytes, any of
        # which can be 0x2E — an ASCII dot — and the split then landed inside
        # the signature. A separator has to be impossible in what it separates.
        token = f"{_b64(payload)}.{_b64(signature)}"
        return PlaybackToken(token=token, playback_id=playback_id, expires_at=expires_at)

    def verify_playback_token(self, *, token: str, playback_id: str) -> bool:
        """Whether this token still authorises this asset.

        Not part of the interface — a real provider verifies at its own edge,
        not here. It exists so the tests can prove the token means something:
        that it expires, and that it does not open a different lesson. Without
        it, "a token was returned" would be the whole assertion.
        """
        try:
            encoded_payload, encoded_signature = token.split(".")
            payload = _unb64(encoded_payload)
            signature = _unb64(encoded_signature)
            signed_id, expiry = payload.decode().rsplit(":", 1)
        except (ValueError, TypeError, binascii.Error):
            return False

        expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        if signed_id != playback_id:
            return False
        return datetime.now(UTC).timestamp() < int(expiry)

    # --- webhooks -------------------------------------------------------

    def sign_webhook(self, *, payload: bytes) -> str:
        """Produce the signature the provider would send.

        Test-side only, and the reason T7's signature check is worth anything:
        a test that could not produce a *valid* signature could only ever
        assert that invalid ones are refused, which a handler rejecting
        everything would also satisfy.
        """
        return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()

    def verify_webhook(self, *, payload: bytes, signature: str) -> None:
        expected = self.sign_webhook(payload=payload)
        # Constant-time: a comparison that returns early leaks how much of a
        # forged signature was right, one byte at a time.
        if not hmac.compare_digest(signature, expected):
            raise WebhookSignatureInvalid

    def parse_webhook(self, *, payload: bytes) -> ProviderWebhookEvent:
        """Normalise a verified payload into our vocabulary."""
        body = json.loads(payload)
        return ProviderWebhookEvent(
            event_id=body["id"],
            event_type=body["type"],
            asset_id=body["asset_id"],
            status=body["status"],
            duration_seconds=body.get("duration_seconds"),
            payload=body,
        )

    def build_webhook(
        self,
        *,
        asset_id: str,
        status: str = ProviderAssetStatus.READY,
        event_id: str | None = None,
        duration_seconds: int | None = 42,
    ) -> tuple[bytes, str]:
        """A payload and its signature, as the provider would send them.

        Test-side. Returning both means a test can replay the *same bytes*
        twice, which is what invariant 8's idempotency actually has to
        survive — re-signing a freshly built payload would produce a new event
        id and test nothing.
        """
        body = {
            "id": event_id or f"fakeevt_{secrets.token_urlsafe(8)}",
            "type": "video.asset.ready"
            if status == ProviderAssetStatus.READY
            else "video.asset.errored",
            "asset_id": asset_id,
            "status": status,
            "duration_seconds": duration_seconds,
        }
        payload = json.dumps(body).encode()
        return payload, self.sign_webhook(payload=payload)


def video_provider() -> FakeVideoProvider:
    """The provider this process should use.

    A function rather than a module-level instance so settings are read when
    it is called. When a real provider is added this is the one place that
    chooses between them — ADR-012 §1's claim that the swap is one file rests
    on nothing else importing a concrete provider directly.
    """
    return FakeVideoProvider()
