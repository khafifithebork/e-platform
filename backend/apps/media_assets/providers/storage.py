"""Object storage — where the master lives.

Invariant 6: **media never passes through Django.** The browser uploads
straight to the store with a presigned URL and Django hands out kilobytes of
JSON. A 2 GB lesson video through a Gunicorn worker would occupy it for
minutes, spend egress on the way back out, and fail on any request-size limit
(architecture.md §3.5).

This is **real S3 code**, not a fake, pointed at MinIO in development and R2 in
production (ADR-012 §1). A fake here would have been actively misleading:
presigned uploads are precisely the thing that goes wrong, and a fake would
accept requests a real store rejects.

---

**A limitation to know about, because it changes what the store enforces.**

A presigned **PUT** cannot cap the size of the upload. The signature covers
the method, key, expiry and — because we sign it — the content type, so a
mismatched type *is* refused by the store. Size is not part of that: whoever
holds the URL can send a hundred gigabytes.

Only a presigned **POST policy** (`content-length-range`) enforces size at the
store. Whether Cloudflare R2 supports presigned POST is **not something I
know, and CLAUDE.md §6 forbids inventing a provider capability** — so it is
marked for verification rather than assumed.

Until that is checked, size is enforced *after* the fact: ``head`` reports the
real byte count, and the service layer refuses and deletes anything over the
limit before the asset advances. That costs one wasted upload rather than
letting an oversized object into the pipeline, and it is strictly weaker than
a store-side cap. **Verify presigned POST against R2 before launch.**
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

# What we accept, and the bytes that prove it. §7 requires checking magic
# bytes rather than the extension, because an extension is whatever the
# uploader typed.
#
# ISO-BMFF (mp4, m4a, mov) puts a four-byte size then "ftyp" at offset 4, so
# the signature is checked at that offset rather than at the start.
MAGIC_SIGNATURES: dict[str, tuple[tuple[int, bytes], ...]] = {
    "video/mp4": (((4, b"ftyp"),)),
    "audio/mp4": (((4, b"ftyp"),)),
    "video/quicktime": (((4, b"ftyp"),)),
    "video/webm": (((0, b"\x1a\x45\xdf\xa3"),)),
    "audio/webm": (((0, b"\x1a\x45\xdf\xa3"),)),
    # MP3 with an ID3 tag, or a bare frame sync.
    "audio/mpeg": ((0, b"ID3"), (0, b"\xff\xfb"), (0, b"\xff\xf3"), (0, b"\xff\xf2")),
}

# How many bytes have to be read back to decide. Small on purpose: this is a
# range request against the store, and reading more would mean pulling the
# object through Django, which is the thing invariant 6 forbids.
MAGIC_PREFIX_BYTES = 16


class UnsupportedContentType(Exception):
    """We do not accept this type, so there is nothing to sign."""


@dataclass(frozen=True)
class PresignedUpload:
    """What the browser needs to upload, and nothing else.

    No credentials, no bucket name, no endpoint the caller could reuse for a
    different key — the URL is scoped to one key, one content type and a short
    expiry.
    """

    url: str
    method: str
    headers: dict[str, str]
    object_key: str
    expires_at: datetime


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    content_type: str
    etag: str


class ObjectStorage(Protocol):
    """What any S3-compatible store must do for us.

    Deliberately small. Django needs to hand out an upload URL, confirm what
    landed, read a few bytes to check the type, and delete. It never reads or
    writes the object itself.
    """

    def presigned_upload(self, *, object_key: str, content_type: str) -> PresignedUpload: ...

    def head(self, *, object_key: str) -> StoredObject | None: ...

    def read_prefix(self, *, object_key: str, length: int = MAGIC_PREFIX_BYTES) -> bytes: ...

    def delete(self, *, object_key: str) -> None: ...


def build_object_key(*, lesson_id, content_type: str) -> str:
    """A key nobody can predict or collide with.

    §7: **randomised object keys, never user-supplied filenames.** A filename
    from the client is a path-traversal string, an overwrite of somebody
    else's object, and a way to smuggle an extension past a check that trusted
    it. None of those exist if the name is generated here.

    The lesson id is a prefix rather than the whole key, so an object can be
    traced back to what it belongs to when reconciling storage against the
    database — but the random component means knowing the lesson id is not
    enough to guess the object.
    """
    extension = {
        "video/mp4": "mp4",
        "audio/mp4": "m4a",
        "video/quicktime": "mov",
        "video/webm": "webm",
        "audio/webm": "weba",
        "audio/mpeg": "mp3",
    }.get(content_type)
    if extension is None:
        raise UnsupportedContentType(content_type)

    return f"masters/{lesson_id}/{secrets.token_urlsafe(24)}.{extension}"


def looks_like(*, prefix: bytes, content_type: str) -> bool:
    """Whether these opening bytes match the declared type.

    Not a full file inspection — the point is to refuse a PHP script named
    `.mp4`, not to validate a container. `python-magic` would do more, and was
    rejected in ADR-012 §2: it needs `libmagic`, a system dependency that
    complicates Windows and CI, and its generality buys nothing against an
    accept-list this short.
    """
    signatures = MAGIC_SIGNATURES.get(content_type)
    if signatures is None:
        return False

    return any(prefix[offset : offset + len(magic)] == magic for offset, magic in signatures)


class S3ObjectStorage:
    """Any S3-compatible store: MinIO in development, R2 in production.

    The difference between them is the endpoint and the credentials, which is
    the whole reason this is real code rather than a fake — the code path
    exercised in tests is the one that runs in production.
    """

    def __init__(self) -> None:
        self.bucket = settings.MEDIA_STORAGE_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.MEDIA_STORAGE_ENDPOINT,
            aws_access_key_id=settings.MEDIA_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.MEDIA_STORAGE_SECRET_KEY,
            region_name=settings.MEDIA_STORAGE_REGION,
            # SigV4 explicitly: R2 requires it, and MinIO accepts it, so both
            # sides are signed the same way and a signing bug shows up locally
            # rather than on first contact with production.
            config=Config(signature_version="s3v4"),
        )

    def presigned_upload(self, *, object_key: str, content_type: str) -> PresignedUpload:
        if content_type not in MAGIC_SIGNATURES:
            raise UnsupportedContentType(content_type)

        expires_in = settings.MEDIA_UPLOAD_URL_TTL_SECONDS
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                # Signed, so the store refuses an upload whose Content-Type
                # does not match what we authorised.
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return PresignedUpload(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            object_key=object_key,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        )

    def head(self, *, object_key: str) -> StoredObject | None:
        """What actually landed, or None if nothing did.

        None rather than an exception for a missing object: "the upload never
        happened" is an expected outcome the caller has to handle, not an
        error condition.
        """
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=object_key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return None
            raise

        return StoredObject(
            key=object_key,
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType", ""),
            etag=response.get("ETag", "").strip('"'),
        )

    def read_prefix(self, *, object_key: str, length: int = MAGIC_PREFIX_BYTES) -> bytes:
        """The first few bytes, by range request.

        A range request, not a download. Invariant 6 forbids pulling the
        object through Django, and sixteen bytes is enough to tell a container
        from a shell script.
        """
        response = self._client.get_object(
            Bucket=self.bucket, Key=object_key, Range=f"bytes=0-{length - 1}"
        )
        return response["Body"].read()

    def delete(self, *, object_key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=object_key)

    def ensure_bucket(self) -> None:
        """Create the bucket if it is missing.

        Development and test only — in production the bucket is created once,
        by whoever holds the account, with lifecycle rules and access policy
        this code has no business setting.
        """
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)


def object_storage() -> ObjectStorage:
    """The store this process should use.

    A function rather than a module-level instance so that settings are read
    when it is called, not at import — which is what lets a test point it at a
    different bucket without reloading the module.
    """
    return S3ObjectStorage()
