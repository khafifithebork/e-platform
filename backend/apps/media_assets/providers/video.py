"""The video provider interface — written before any vendor code.

architecture.md §10 M5: "the provider interface (``create_asset``,
``get_playback_token``, ``delete_asset``) is the thing that keeps video
migratable. Write it before the Mux code." So this exists first, and the only
implementation in M5 is a fake (ADR-012 §1).

**Nothing here describes a real provider's API.** The vocabulary is ours. Mux
is named in the architecture document but has not been signed up for, and §6
forbids inventing a provider's capabilities — so M8's adapter will *translate*
whatever the chosen provider sends into these shapes, rather than these shapes
being modelled on a provider nobody has read the documentation for yet.

**Two rules the interface enforces by its types.**

An adapter returns **opaque ids, never URLs** (invariant 7). ``MediaAsset`` has
a ``CheckConstraint`` refusing ``://`` in either id column, so an adapter that
returned a playback URL would fail at the database rather than quietly storing
something that makes the provider unswappable.

An adapter **never touches the ORM**. It takes and returns plain data; the
service layer decides what that means for our rows. Same seam M4's billing
provider established, and the reason swapping a provider is one file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


class ProviderAssetStatus:
    """What a provider can tell us about an asset, in our words.

    Three states, because that is all the pipeline needs to know: it is being
    worked on, it can be played, or it went wrong. A provider with fifteen
    internal states maps them onto these.
    """

    PROCESSING = "PROCESSING"
    READY = "READY"
    ERRORED = "ERRORED"


@dataclass(frozen=True)
class ProviderAsset:
    """A provider's view of one asset.

    ``asset_id`` and ``playback_id`` are opaque handles. They are *not* URLs,
    and the database refuses them if they look like one.
    """

    provider: str
    asset_id: str
    playback_id: str
    status: str
    duration_seconds: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PlaybackToken:
    """Permission to play one asset, for a short time.

    Carries the playback id because the player needs both, and an expiry
    because architecture.md §7 requires a short TTL: a token that does not
    expire is a permanent share link for paid content, and the entitlement
    check that produced it becomes a one-off rather than a gate.

    **Not a URL.** The player composes one; we hand out a handle and a token,
    so changing provider does not change what is stored or what was ever sent.
    """

    token: str
    playback_id: str
    expires_at: datetime


@dataclass(frozen=True)
class ProviderWebhookEvent:
    """A webhook, normalised, before anything is done about it.

    ``event_id`` is what invariant 8's idempotency table is unique on, so it
    must be the provider's own id for the event and not something we derive —
    a derived id would differ between two deliveries of the same event, which
    is exactly the case the table exists to catch.
    """

    event_id: str
    event_type: str
    asset_id: str
    status: str
    duration_seconds: int | None = None
    payload: dict = field(default_factory=dict)


class WebhookSignatureInvalid(Exception):
    """The payload did not come from the provider, or was altered."""


@runtime_checkable
class VideoProvider(Protocol):
    """What any video provider must do for us.

    Small on purpose: everything here is exercised by M5. There is no
    speculative surface for capabilities no provider has been chosen to have.
    """

    name: str

    def create_asset(self, *, source_url: str) -> ProviderAsset:
        """Ask the provider to ingest a master from a URL it can fetch.

        A URL rather than bytes, because invariant 6 forbids media passing
        through Django and architecture.md §3.5 has the provider pulling from
        our storage directly. The URL is short-lived and read-only.
        """
        ...

    def get_playback_token(self, *, playback_id: str, ttl_seconds: int) -> PlaybackToken:
        """Mint permission to play.

        §7: "a token minted without checking entitlement is a valid token for
        content the user hasn't paid for. The check and the mint live in one
        service function, in that order, always." This adapter does not know
        about entitlement and must not — it is the enforcement, not the
        decision.
        """
        ...

    def delete_asset(self, *, asset_id: str) -> None:
        """Remove the derived copy. The master in our storage is untouched —
        that asymmetry is what makes a provider migration a re-upload script
        rather than an email to every instructor."""
        ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> None:
        """Raise ``WebhookSignatureInvalid`` unless the payload is authentic.

        Invariant 8 puts this **first**, before the event is even recorded: an
        unverified webhook is an unauthenticated write to subscription or media
        state, and recording it first would mean an attacker could fill the
        idempotency table with ids the real provider would later be refused
        for.
        """
        ...

    def parse_webhook(self, *, payload: bytes) -> ProviderWebhookEvent:
        """Normalise a verified payload. Never called before verification."""
        ...
