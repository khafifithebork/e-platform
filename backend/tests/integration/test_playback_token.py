"""Minting permission to play — the endpoint architecture.md §7 is bluntest about.

"Signed playback tokens are not access control on their own. They're the
*enforcement*; the *decision* is the entitlement resolver. A token minted
without checking entitlement is a valid token for content the user hasn't paid
for."

So the test that matters most is abuse case 6, and it is not "the response
contained no token". It is **the provider adapter was never called**. Those are
different claims: a mint that happens and is then discarded by the view still
produced a valid, signed, working token for content nobody paid for — and
nothing in the response would show it. §10 M5 asks for exactly this assertion.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.media_assets.providers.fake_video import FakeVideoProvider

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


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test", Role.INSTRUCTOR)


@pytest.fixture
def lesson(db, instructor):
    """A published lesson whose media is ready to play."""
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
    MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
        duration_seconds=181,
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return lesson


@pytest.fixture
def subscriber(db):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    user = _user("payer@example.test")
    start_subscription(user=user, provider=FakeBillingProvider())
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/playback-token/"


class TestNoTokenIsMintedOnDenial:
    """Abuse case 6, and §10 M5's explicit requirement."""

    def test_the_provider_is_never_asked_when_entitlement_is_denied(self, client, lesson) -> None:
        """The assertion that matters. "The response had no token" is a weaker
        claim: a mint that happens and is discarded still produced a valid,
        signed, working token, and nothing in the response would show it."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        with patch.object(FakeVideoProvider, "get_playback_token") as mint:
            response = client.post(_url(lesson))

        assert response.status_code == 403
        assert not mint.called, "a token was minted for someone who may not watch"

    def test_the_provider_is_never_asked_for_an_anonymous_caller(self, client, lesson) -> None:
        with patch.object(FakeVideoProvider, "get_playback_token") as mint:
            response = client.post(_url(lesson))

        assert response.status_code == 403
        assert not mint.called

    def test_the_provider_is_never_asked_once_a_subscription_ends(
        self, client, lesson, subscriber
    ) -> None:
        """Provoked in both directions: the same caller, before and after."""
        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        _sign_in(client, "payer@example.test")
        assert client.post(_url(lesson)).status_code == 200

        cancel(
            subscription=Subscription.objects.get(user=subscriber),
            provider=FakeBillingProvider(),
            immediately=True,
        )

        with patch.object(FakeVideoProvider, "get_playback_token") as mint:
            assert client.post(_url(lesson)).status_code == 403
        assert not mint.called

    def test_the_denial_carries_a_reason_and_a_cta(self, client, lesson) -> None:
        """EntitlementDenied is not caught and rebuilt by hand in the view —
        that is how the reason gets lost (ADR-004)."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        body = client.post(_url(lesson)).json()

        assert body["type"] == "/problems/entitlement-denied"
        assert body["reason"] == "NO_SUBSCRIPTION"
        assert body["cta"] == "subscribe"


class TestEveryEntitlementBranchReachesTheRightAnswer:
    """§10 M5: "every entitlement branch". The resolver is unit-tested to 100%
    branch coverage in M4; this checks the branches arrive here intact."""

    def test_a_subscriber_gets_a_token(self, client, lesson, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        response = client.post(_url(lesson))

        assert response.status_code == 200
        assert response.json()["token"]

    def test_a_preview_lesson_plays_with_no_account(self, client, lesson) -> None:
        """§10 M5 asks for this by name. AllowAny on the view is what lets the
        resolver's first branch run at all — IsAuthenticated would refuse a
        preview before entitlement was consulted."""
        from apps.catalog.models import Lesson

        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)

        assert client.post(_url(lesson)).status_code == 200

    def test_the_instructor_may_play_their_own_lesson(self, client, lesson) -> None:
        """Also asked for by name. An instructor who cannot watch their own
        course cannot check their own work."""
        _sign_in(client, "teacher@example.test")

        assert client.post(_url(lesson)).status_code == 200

    def test_an_admin_may_play(self, client, lesson) -> None:
        _user("boss@example.test", Role.ADMIN)
        _sign_in(client, "boss@example.test")

        assert client.post(_url(lesson)).status_code == 200

    def test_an_override_is_enough(self, client, lesson) -> None:
        """A manual grant reaches this endpoint like any other allow-branch."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.entitlements.models import AccessOverride

        student = _user("guest@example.test")
        admin = _user("granter@example.test", Role.ADMIN)
        now = timezone.now()
        AccessOverride.objects.create(
            user=student,
            granted_by=admin,
            reason="Compensation.",
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(days=7),
        )
        _sign_in(client, "guest@example.test")

        assert client.post(_url(lesson)).status_code == 200


class TestVisibilityStillApplies:
    def test_an_unpublished_lesson_is_a_404_even_for_a_subscriber(
        self, client, lesson, subscriber
    ) -> None:
        """The resolver knows about subscriptions, not publication. Without
        the visibility gate a paying subscriber could play a draft the
        instructor never submitted."""
        from apps.catalog.models import Course

        Course.objects.filter(pk=lesson.course_id).update(status="DRAFT")
        _sign_in(client, "payer@example.test")

        with patch.object(FakeVideoProvider, "get_playback_token") as mint:
            response = client.post(_url(lesson))

        assert response.status_code == 404
        assert not mint.called


class TestWhenTheMediaIsNotReady:
    def test_an_unprocessed_asset_is_a_409_not_a_403(self, client, lesson, subscriber) -> None:
        """They may watch it; there is simply nothing transcoded yet.
        Reporting this as an entitlement problem would send a paying
        subscriber to the upgrade page for a failure that is ours."""
        MediaAsset.objects.filter(lesson=lesson).update(status=MediaAssetStatus.TRANSCODING)
        _sign_in(client, "payer@example.test")

        response = client.post(_url(lesson))

        assert response.status_code == 409
        assert response.json()["status"] == "TRANSCODING"

    def test_a_lesson_with_no_media_is_a_409(self, client, lesson, subscriber) -> None:
        MediaAsset.objects.filter(lesson=lesson).delete()
        _sign_in(client, "payer@example.test")

        assert client.post(_url(lesson)).status_code == 409

    def test_entitlement_is_still_checked_first(self, client, lesson) -> None:
        """Order matters even when both would refuse: answering 409 to someone
        unentitled tells them the lesson exists and is merely unprocessed."""
        MediaAsset.objects.filter(lesson=lesson).update(status=MediaAssetStatus.TRANSCODING)
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        assert client.post(_url(lesson)).status_code == 403


class TestWhatTheTokenCarries:
    def test_the_token_actually_authorises_this_asset(self, client, lesson, subscriber) -> None:
        """Not merely that a string came back. The fake verifies for real, so
        this proves the token is signed, unexpired and scoped to this
        lesson's playback id."""
        _sign_in(client, "payer@example.test")

        body = client.post(_url(lesson)).json()

        assert FakeVideoProvider().verify_playback_token(
            token=body["token"], playback_id="fakeplay_abc"
        )

    def test_the_token_does_not_open_another_lesson(self, client, lesson, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        body = client.post(_url(lesson)).json()

        assert not FakeVideoProvider().verify_playback_token(
            token=body["token"], playback_id="fakeplay_somebody_else"
        )

    def test_no_playback_url_is_returned(self, client, lesson, subscriber) -> None:
        """Abuse case 11, invariant 7. We return a handle and a token; the
        player composes the URL, so changing provider changes nothing we ever
        sent."""
        _sign_in(client, "payer@example.test")

        response = client.post(_url(lesson))

        assert b"://" not in response.content

    def test_the_expiry_is_returned(self, client, lesson, subscriber) -> None:
        """So a player can refresh before playback dies mid-lesson rather than
        discovering the expiry by failing."""
        _sign_in(client, "payer@example.test")

        assert client.post(_url(lesson)).json()["expires_at"]

    def test_the_playback_id_reaches_only_an_entitled_caller(
        self, client, lesson, subscriber
    ) -> None:
        """Abuse case 10. It is the handle that plays the video: an entitled
        caller needs it, and it appears nowhere else — not in the instructor's
        asset view, not in the catalogue."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")
        denied = client.post(_url(lesson))

        client.post("/api/v1/auth/logout/")
        _sign_in(client, "payer@example.test")
        allowed = client.post(_url(lesson))

        assert b"fakeplay_abc" not in denied.content
        assert b"fakeplay_abc" in allowed.content
