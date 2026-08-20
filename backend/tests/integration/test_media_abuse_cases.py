"""The M5 abuse cases nothing else covers, and the query costs.

Cases 1, 3, 4 and 5 are proven by `test_media_upload.py`, 6 by
`test_playback_token.py`, and 7, 8 and 9 by `test_media_webhook.py`. Three
remain, and they are the ones that cannot live beside a single endpoint:

- **2** — the *store* rejects a mismatched content type, not us being polite
  about it afterwards.
- **10** — `provider_playback_id` reaches an entitled caller and nobody else,
  across every endpoint rather than the one it was noticed on.
- **11** — no response anywhere contains a playback URL (invariant 7),
  asserted against raw bytes.

Cases 10 and 11 are swept rather than spot-checked on purpose. A leak is a
property of the *system*, and checking the endpoint you happened to think of
is how the next endpoint leaks.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus

PASSWORD = "a-long-enough-passphrase"
MP4_BYTES = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 128
PLAYBACK_ID = "fakeplay_secret_handle"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture(autouse=True)
def _bucket():
    from apps.media_assets.providers.storage import object_storage

    store = object_storage()
    try:
        store.ensure_bucket()
    except Exception as exc:
        pytest.skip(f"object storage unavailable: {exc}")
    return store


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
    """A published lesson with ready media."""
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", body="Paid.", position=1
    )
    MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id=PLAYBACK_ID,
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


class TestTheStoreEnforcesTheContentType:
    """Abuse case 2.

    The presigned PUT signs the content type, so the *store* refuses an upload
    that does not match — the caller cannot substitute a different type using a
    URL we handed them. That is a different guarantee from checking afterwards,
    which is what the size limit has to settle for (see providers/storage.py:
    a presigned PUT cannot cap size, and presigned POST against R2 is marked
    for verification).
    """

    @pytest.fixture
    def fresh_lesson(self, db, instructor):
        """A lesson with no media yet.

        The `lesson` fixture already has a READY asset, and requesting a
        replacement upload for one is a 409 by design (T4) — so these tests
        need a lesson that has never been uploaded to.
        """
        from apps.catalog.models import Course, Language, Lesson, Section

        language, _ = Language.objects.get_or_create(
            code="fr", defaults={"name": "French", "native_name": "Francais"}
        )
        course = Course.objects.create(
            slug="french", title="French", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="Bonjour", position=1)
        return Lesson.objects.create(
            course=course, section=section, slug="bonjour", title="Bonjour", position=1
        )

    def _ticket(self, client, lesson):
        return client.post(
            f"/api/v1/lessons/{lesson.id}/media/upload-url/",
            {"content_type": "video/mp4"},
            content_type="application/json",
        ).json()

    def _put(self, upload, body: bytes, content_type: str) -> int:
        request = urllib.request.Request(  # noqa: S310 — our own signed URL
            upload["url"],
            data=body,
            method=upload["method"],
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_the_signed_content_type_is_honoured(self, client, fresh_lesson) -> None:
        """The positive twin: with the type we signed, the store accepts it."""
        _sign_in(client, "teacher@example.test")
        ticket = self._ticket(client, fresh_lesson)

        assert self._put(ticket["upload"], MP4_BYTES, "video/mp4") == 200

    def test_a_different_content_type_is_refused_by_the_store(self, client, fresh_lesson) -> None:
        """Refused before the bytes are stored, not tidied up afterwards. The
        signature covers the content type, so changing it invalidates it."""
        _sign_in(client, "teacher@example.test")
        ticket = self._ticket(client, fresh_lesson)

        status_code = self._put(ticket["upload"], b"<?php ?>" + b"\x00" * 64, "application/x-php")

        assert status_code == 403

    def test_nothing_is_stored_when_the_store_refuses(self, client, fresh_lesson, _bucket) -> None:
        """The half that matters for the bill: a refused upload leaves no
        object behind."""
        _sign_in(client, "teacher@example.test")
        ticket = self._ticket(client, fresh_lesson)
        key = ticket["upload"]["object_key"]

        self._put(ticket["upload"], b"<?php ?>" + b"\x00" * 64, "application/x-php")

        assert _bucket.head(object_key=key) is None


class TestNoResponseLeaksAPlaybackHandleOrUrl:
    """Abuse cases 10 and 11, swept across every media-touching endpoint.

    Spot-checking the endpoint you happened to think of is how the next one
    leaks, so this enumerates them. `provider_playback_id` is the handle that
    plays the video: it belongs in a minted token and nowhere else. A playback
    *URL* belongs nowhere at all (invariant 7) — storing or sending one is what
    makes a provider unswappable.
    """

    def _every_readable_path(self, lesson) -> list[str]:
        asset = MediaAsset.objects.get(lesson=lesson)
        return [
            "/api/v1/catalogue/courses/",
            f"/api/v1/catalogue/courses/{lesson.course.slug}/",
            f"/api/v1/lessons/{lesson.id}/",
            f"/api/v1/media-assets/{asset.id}/",
            "/api/v1/auth/me/",
        ]

    def test_no_get_endpoint_returns_the_playback_handle(self, client, lesson, subscriber) -> None:
        """Even for an entitled caller: being allowed to watch means being
        given a token, not being handed the handle to keep."""
        _sign_in(client, "payer@example.test")

        for path in self._every_readable_path(lesson):
            assert PLAYBACK_ID.encode() not in client.get(path).content, path

    def test_the_instructors_own_asset_view_does_not_either(self, client, lesson) -> None:
        """The most tempting place to expose it, and still no."""
        _sign_in(client, "teacher@example.test")

        for path in self._every_readable_path(lesson):
            assert PLAYBACK_ID.encode() not in client.get(path).content, path

    def test_no_response_contains_a_url_to_the_provider(self, client, lesson, subscriber) -> None:
        """Invariant 7 asserted against raw bytes rather than a field name, so
        a URL nested anywhere in a payload still fails."""
        _sign_in(client, "payer@example.test")
        paths = self._every_readable_path(lesson)

        for path in paths:
            content = client.get(path).content
            assert b"fakeplay" not in content, path
            assert b"mux.com" not in content, path

    def test_the_playback_endpoint_is_the_one_exception(self, client, lesson, subscriber) -> None:
        """The positive twin. A sweep that found the handle nowhere would also
        pass if the token endpoint had stopped returning it, and playback
        would be quietly broken."""
        _sign_in(client, "payer@example.test")

        body = client.post(f"/api/v1/lessons/{lesson.id}/playback-token/").json()

        assert body["playback_id"] == PLAYBACK_ID
        assert "://" not in body["token"]


class TestQueryCosts:
    """ADR-009: measured, and pinned at two dataset sizes where fan-out is
    possible."""

    def test_minting_a_token_costs_a_fixed_number_of_queries(
        self, client, lesson, subscriber, django_assert_num_queries
    ) -> None:
        """Called every time a learner opens a lesson, so it sits on the
        hottest authenticated path after the lesson itself.

        Session, user, the lesson with its course, the resolver's override and
        subscription checks, and the media asset.
        """
        _sign_in(client, "payer@example.test")

        with django_assert_num_queries(6):
            client.post(f"/api/v1/lessons/{lesson.id}/playback-token/")

    def test_the_asset_status_endpoint_does_not_fan_out(
        self, client, lesson, django_assert_num_queries
    ) -> None:
        """Session, user, and the asset joined to its lesson and course — the
        join is what keeps the ownership check from costing two more."""
        asset = MediaAsset.objects.get(lesson=lesson)
        _sign_in(client, "teacher@example.test")

        with django_assert_num_queries(3):
            client.get(f"/api/v1/media-assets/{asset.id}/")

    def test_the_webhook_receiver_is_cheap(self, client, lesson) -> None:
        """It runs on every provider event and must stay a thin insert:
        anything slow here is a request the provider may time out and repeat.

        Savepoints are filtered out: pytest-django wraps each test in a
        transaction, so `transaction.atomic()` becomes a savepoint pair that
        production does not pay. Counting them would pin a number that only
        exists under test.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.media_assets.providers.fake_video import FakeVideoProvider

        payload, signature = FakeVideoProvider().build_webhook(asset_id="fakeasset_abc")

        with CaptureQueriesContext(connection) as captured:
            client.post(
                "/api/v1/webhooks/video/",
                data=payload,
                content_type="application/json",
                HTTP_X_WEBHOOK_SIGNATURE=signature,
            )

        real = [
            query for query in captured.captured_queries if "SAVEPOINT" not in query["sql"].upper()
        ]

        assert len(real) == 1, [query["sql"] for query in real]
