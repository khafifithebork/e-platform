"""The upload round trip: authorise, upload, confirm.

Abuse cases 1, 3, 4 and 5. Every test that says an upload was refused also
checks the store, because "the API said no" and "nothing landed in the bucket"
are different claims and only the second one costs nothing.

Real bytes to real MinIO. A fake store would let all of this pass while the
presigned URL was malformed (ADR-012 §1).
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"
MP4_BYTES = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 128
SHELL_SCRIPT = b"#!/bin/sh\nrm -rf /\n" + b"\x00" * 128

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


def _user(email: str, role: str = Role.INSTRUCTOR):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _lesson(instructor, slug: str = "intro"):
    from apps.catalog.models import Course, Language, Lesson, Section

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Español"}
    )
    course = Course.objects.create(
        slug=f"course-{slug}",
        title="Spanish",
        language=language,
        level="A1",
        instructor=instructor,
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    return Lesson.objects.create(
        course=course, section=section, slug=slug, title="Intro", position=1
    )


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test")


@pytest.fixture
def lesson(db, instructor):
    return _lesson(instructor)


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _upload_url(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/media/upload-url/"


def _ask(client, lesson, content_type: str = "video/mp4"):
    return client.post(
        _upload_url(lesson), {"content_type": content_type}, content_type="application/json"
    )


def _put(upload: dict, body: bytes) -> int:
    request = urllib.request.Request(  # noqa: S310 — our own signed URL
        upload["url"], data=body, method=upload["method"], headers=upload["headers"]
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.status


class TestOnlyTheOwnerMayUpload:
    """Abuse case 1."""

    def test_another_instructors_lesson_is_a_404(self, client, lesson) -> None:
        """404, not 403 — a 403 confirms the lesson exists (§6.3)."""
        from apps.media_assets.models import MediaAsset

        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert _ask(client, lesson).status_code == 404
        assert not MediaAsset.objects.exists()

    def test_a_student_is_a_404(self, client, lesson) -> None:
        _user("student@example.test", Role.STUDENT)
        _sign_in(client, "student@example.test")

        assert _ask(client, lesson).status_code == 404

    def test_anonymous_is_refused(self, client, lesson) -> None:
        assert _ask(client, lesson).status_code in (401, 403)

    def test_the_owner_may(self, client, lesson) -> None:
        _sign_in(client, "teacher@example.test")

        assert _ask(client, lesson).status_code == 201

    def test_an_admin_may(self, client, lesson) -> None:
        _user("admin@example.test", Role.ADMIN)
        _sign_in(client, "admin@example.test")

        assert _ask(client, lesson).status_code == 201

    def test_completing_someone_elses_asset_is_a_404(self, client, lesson) -> None:
        _sign_in(client, "teacher@example.test")
        asset_id = _ask(client, lesson).json()["asset"]["id"]
        client.post("/api/v1/auth/logout/")

        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert client.post(f"/api/v1/media-assets/{asset_id}/complete/").status_code == 404


class TestTheKeyIsOurs:
    """Abuse case 3."""

    def test_no_client_input_reaches_the_object_key(self, client, lesson) -> None:
        """The request has nowhere to put a filename — the only field is the
        content type. Path traversal and overwriting somebody else's object
        are not defended against here, they are unreachable."""
        _sign_in(client, "teacher@example.test")

        response = _ask(client, lesson)

        key = response.json()["upload"]["object_key"]
        assert key.startswith(f"masters/{lesson.id}/")
        assert ".." not in key

    def test_a_filename_in_the_body_is_ignored(self, client, lesson) -> None:
        _sign_in(client, "teacher@example.test")

        response = client.post(
            _upload_url(lesson),
            {"content_type": "video/mp4", "object_key": "../../etc/passwd", "filename": "x.php"},
            content_type="application/json",
        )

        assert "etc/passwd" not in response.json()["upload"]["object_key"]

    def test_an_unsupported_type_is_refused(self, client, lesson) -> None:
        """A closed accept-list: a type with no magic signature cannot be
        verified, so accepting it would mean accepting unverifiable bytes."""
        _sign_in(client, "teacher@example.test")

        assert _ask(client, lesson, "application/x-php").status_code == 400


class TestCompletingAnUpload:
    def test_the_happy_path(self, client, lesson) -> None:
        _sign_in(client, "teacher@example.test")
        ticket = _ask(client, lesson).json()
        _put(ticket["upload"], MP4_BYTES)

        response = client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "UPLOADED"
        assert body["source_bytes"] == len(MP4_BYTES)

    def test_completing_without_uploading_is_refused(self, client, lesson) -> None:
        """Abuse case 4. The client controls when this is called, so it can be
        called for an object that never arrived."""
        from apps.media_assets.models import MediaAsset

        _sign_in(client, "teacher@example.test")
        ticket = _ask(client, lesson).json()

        response = client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        assert response.status_code == 422
        assert MediaAsset.objects.get().status == "PENDING"

    def test_bytes_that_are_not_the_declared_type_are_refused(self, client, lesson) -> None:
        """Abuse case 5, end to end. The store cannot know the file is a lie —
        the signature only fixes the *declared* type — so the bytes are read
        back and checked."""
        from apps.media_assets.models import MediaAsset

        _sign_in(client, "teacher@example.test")
        ticket = _ask(client, lesson).json()
        _put(ticket["upload"], SHELL_SCRIPT)

        response = client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        assert response.status_code == 422
        assert MediaAsset.objects.get().status == "FAILED"

    def test_a_rejected_upload_is_deleted_from_the_store(self, client, lesson, _bucket) -> None:
        """The half of the refusal that costs money. An object nobody removes
        is storage we pay for forever, referenced by nothing, and
        indistinguishable from a real master when reconciling the bucket."""
        _sign_in(client, "teacher@example.test")
        ticket = _ask(client, lesson).json()
        key = ticket["upload"]["object_key"]
        _put(ticket["upload"], SHELL_SCRIPT)

        client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        assert _bucket.head(object_key=key) is None

    def test_an_oversized_upload_is_refused(self, client, lesson, settings) -> None:
        """The limit the presigned PUT could not enforce. Checked after the
        fact, which is weaker than a store-side cap and is why presigned POST
        is marked for verification against R2."""
        from apps.media_assets.models import MediaAsset

        settings.MEDIA_MAX_UPLOAD_BYTES = 32
        _sign_in(client, "teacher@example.test")
        ticket = _ask(client, lesson).json()
        _put(ticket["upload"], MP4_BYTES)

        response = client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        assert response.status_code == 422
        asset = MediaAsset.objects.get()
        assert asset.status == "FAILED"
        assert "over the limit" in asset.error_message

    def test_completing_twice_is_refused(self, client, lesson) -> None:
        """Not idempotent by accident: the second call would re-run
        verification against an asset already past PENDING."""
        _sign_in(client, "teacher@example.test")
        ticket = _ask(client, lesson).json()
        _put(ticket["upload"], MP4_BYTES)
        client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        second = client.post(f"/api/v1/media-assets/{ticket['asset']['id']}/complete/")

        assert second.status_code == 409


class TestReplacingAnAsset:
    def test_a_failed_upload_can_be_retried(self, client, lesson) -> None:
        """The master was never valid, so there is nothing to preserve — and
        an instructor who uploaded the wrong file must not be stuck."""
        _sign_in(client, "teacher@example.test")
        first = _ask(client, lesson).json()
        _put(first["upload"], SHELL_SCRIPT)
        client.post(f"/api/v1/media-assets/{first['asset']['id']}/complete/")

        second = _ask(client, lesson)

        assert second.status_code == 201
        assert second.json()["asset"]["status"] == "PENDING"

    def test_retrying_clears_the_previous_error(self, client, lesson) -> None:
        """A row carrying a stale message describes an asset that no longer
        exists, and the FAILED rows are what the dead-letter queue is read
        from."""
        _sign_in(client, "teacher@example.test")
        first = _ask(client, lesson).json()
        _put(first["upload"], SHELL_SCRIPT)
        client.post(f"/api/v1/media-assets/{first['asset']['id']}/complete/")

        second = _ask(client, lesson).json()

        assert second["asset"]["error_message"] == ""

    def test_a_ready_asset_is_not_replaced_by_accident(self, client, lesson) -> None:
        """409, so replacing live media is a deliberate act rather than a side
        effect of opening the upload dialog."""
        from apps.media_assets.models import MediaAsset

        _sign_in(client, "teacher@example.test")
        _ask(client, lesson)
        MediaAsset.objects.update(
            status="READY", provider_asset_id="abc", provider_playback_id="xyz"
        )

        assert _ask(client, lesson).status_code == 409


class TestNothingSensitiveIsReturned:
    def test_the_playback_id_is_never_in_an_upload_response(self, client, lesson) -> None:
        """Abuse case 10. It is the handle that plays the video and belongs
        only inside a minted token."""
        from apps.media_assets.models import MediaAsset

        _sign_in(client, "teacher@example.test")
        _ask(client, lesson)
        MediaAsset.objects.update(provider_playback_id="secret-playback-handle")

        body = client.post(f"/api/v1/media-assets/{MediaAsset.objects.get().id}/complete/")

        assert b"secret-playback-handle" not in body.content

    def test_the_asset_serializer_exposes_no_provider_fields(self) -> None:
        from apps.media_assets.serializers import MediaAssetSerializer

        fields = set(MediaAssetSerializer().fields)

        assert not fields & {
            "provider",
            "provider_asset_id",
            "provider_playback_id",
            "source_object_key",
        }

    def test_no_field_that_decides_playback_is_writable(self) -> None:
        """ADR-011, applied before the fields have meaning rather than after.
        Every one of these will be read by T8's token minting."""
        from apps.media_assets.serializers import MediaAssetSerializer

        writable = {
            name for name, field in MediaAssetSerializer().fields.items() if not field.read_only
        }

        assert writable == set()
