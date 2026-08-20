"""Upload orchestration — the writes, and nothing that decides access.

Django's part of an upload is two short JSON exchanges: hand out a signed URL,
then confirm what landed. The bytes go browser → store and never touch this
process (invariant 6).

**Verification is synchronous; processing is not.** ``complete_upload`` does a
``head`` and a sixteen-byte range read before returning, because "that file is
not a video" has to reach the person who just uploaded it, while they still
have the file open. Transcoding takes minutes and belongs to a task. Splitting
them the other way — accepting anything and reporting the failure by email
later — is how an instructor discovers on publication day that nothing worked.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction

from apps.accounts.models import Role, User
from apps.catalog.models import Lesson
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.media_assets.providers.storage import (
    ObjectStorage,
    PresignedUpload,
    UnsupportedContentType,
    build_object_key,
    looks_like,
)
from apps.media_assets.tasks import process_media_asset

# States an upload may replace. TRANSCODING is excluded because the provider is
# mid-job on the current master, and READY because replacing live media is a
# deliberate act rather than a side effect of opening the upload dialog.
REPLACEABLE = (
    MediaAssetStatus.PENDING,
    MediaAssetStatus.UPLOADED,
    MediaAssetStatus.FAILED,
)


class NotYours(Exception):
    """This lesson is not one the caller may manage.

    Separate from ``UploadNotAllowed`` because the two produce different
    answers and must not be told apart by reading an error message: this is a
    404 (§6.3 — never confirm the thing exists), a state conflict is a 409.
    Matching on message text would make the status code depend on wording.
    """


class UploadNotAllowed(Exception):
    """The asset is not in a state that accepts a new upload."""


class UploadVerificationFailed(Exception):
    """What landed is not what was authorised."""


def _may_manage(lesson: Lesson, user: User) -> bool:
    """Who may put media on a lesson.

    Its own function so the answer is in one place, and deliberately *not* the
    entitlement resolver: that decides who may *watch*, this decides who may
    *replace*. Merging them would mean every subscriber could overwrite an
    instructor's master, which is what happens the first time somebody reuses
    ``resolve_access`` because it was nearby.
    """
    if getattr(user, "role", None) == Role.ADMIN or getattr(user, "is_superuser", False):
        return True
    return lesson.course.instructor_id == user.pk


@transaction.atomic
def request_upload(
    *, lesson: Lesson, by: User, content_type: str, storage: ObjectStorage
) -> tuple[MediaAsset, PresignedUpload]:
    """Authorise one upload, for one key, for a short time.

    The object key is generated here and never taken from the client (§7), so
    a filename cannot become a path, an overwrite, or an extension that lies.

    The asset row is created *before* the upload, in ``PENDING``. That is what
    makes an abandoned upload visible: a row with no object behind it is a
    person who started and gave up, which is a fact worth having rather than
    silence.
    """
    if not _may_manage(lesson, by):
        raise NotYours

    asset = MediaAsset.objects.select_for_update().filter(lesson=lesson).first()
    if asset is not None and asset.status not in REPLACEABLE:
        raise UploadNotAllowed(f"An asset in {asset.status} cannot be replaced.")

    object_key = build_object_key(lesson_id=lesson.pk, content_type=content_type)
    upload = storage.presigned_upload(object_key=object_key, content_type=content_type)

    if asset is None:
        asset = MediaAsset(lesson=lesson)

    # A replacement starts clean. Carrying a previous run's error message or
    # provider ids forward would leave the row describing an asset that no
    # longer exists.
    asset.source_object_key = object_key
    # Not yet uploaded, but the column is NOT NULL and constrained positive.
    # One is a placeholder the completion step overwrites with the real size;
    # zero would violate `source_has_bytes`, which exists to catch exactly the
    # empty object this is not yet.
    asset.source_bytes = 1
    asset.provider = ""
    asset.provider_asset_id = ""
    asset.provider_playback_id = ""
    asset.status = MediaAssetStatus.PENDING
    asset.error_message = ""
    asset.retry_count = 0
    asset.save()

    return asset, upload


def _fail(asset: MediaAsset, message: str, storage: ObjectStorage) -> None:
    """Record the failure and remove the object it refers to.

    Deleting matters: a rejected upload nobody removes is an object we pay to
    store forever, referenced by nothing, indistinguishable from a real master
    when someone reconciles the bucket against the database.
    """
    storage.delete(object_key=asset.source_object_key)
    asset.status = MediaAssetStatus.FAILED
    asset.error_message = message
    asset.save(update_fields=["status", "error_message", "updated_at"])


def complete_upload(*, asset: MediaAsset, by: User, storage: ObjectStorage) -> MediaAsset:
    """Confirm what the browser says it uploaded, or refuse it.

    **Deliberately not wrapped in a transaction**, and that is load-bearing.
    It was, and the failure path then recorded FAILED and raised — which rolled
    the record back on the way out. Every rejected upload stayed PENDING with
    no error message, so the dead-letter queue was permanently empty while
    looking like it worked. A failure has to survive the exception that reports
    it; only the success write needs to be atomic, and it is a single row.

    Three checks, in order of cost. Each has an abuse case behind it and none
    of them trusts the client:

    1. **It exists.** A client can call this without uploading anything.
    2. **It is not too large.** The size limit the presigned PUT could not
       enforce (see ``providers/storage.py``) — so it is enforced here, after
       the fact, which is weaker and is why the store-side option is marked
       for verification.
    3. **It is what it claims.** Magic bytes, not the extension, and not the
       ``Content-Type`` the store recorded — the store only knows what the
       uploader declared.
    """
    if not _may_manage(asset.lesson, by):
        raise NotYours
    if asset.status != MediaAssetStatus.PENDING:
        raise UploadNotAllowed(f"An asset in {asset.status} is not awaiting an upload.")

    stored = storage.head(object_key=asset.source_object_key)
    if stored is None:
        # No object, so nothing to delete and nothing to record against it —
        # the asset stays PENDING and the same URL can still be used.
        raise UploadVerificationFailed("No upload was received.")

    if stored.size_bytes > settings.MEDIA_MAX_UPLOAD_BYTES:
        _fail(asset, f"File is {stored.size_bytes} bytes, over the limit.", storage)
        raise UploadVerificationFailed("File is too large.")

    prefix = storage.read_prefix(object_key=asset.source_object_key)
    if not looks_like(prefix=prefix, content_type=stored.content_type):
        _fail(asset, "File contents do not match the declared type.", storage)
        raise UploadVerificationFailed("File contents do not match the declared type.")

    with transaction.atomic():
        asset.source_bytes = stored.size_bytes
        asset.source_checksum = stored.etag
        asset.status = MediaAssetStatus.UPLOADED
        asset.save(update_fields=["source_bytes", "source_checksum", "status", "updated_at"])

    # Enqueued after the row is committed, not inside the atomic block above.
    # A worker is a separate process and can pick the task up immediately —
    # before an uncommitted transaction is visible to it — and would then read
    # an asset still in PENDING and decline to act. `on_commit` is what makes
    # the ordering certain rather than usually fine.
    transaction.on_commit(lambda: process_media_asset.delay(str(asset.pk)))

    return asset


@transaction.atomic
def retry_processing(*, asset: MediaAsset) -> MediaAsset:
    """Put a dead-lettered asset back through the pipeline.

    The point of the master being ours: the file is still in storage, so a
    failure caused by a provider outage costs a click rather than asking an
    instructor to upload two gigabytes again.

    Only from FAILED. Retrying something mid-flight would race the task that
    is already running it.
    """
    if asset.status != MediaAssetStatus.FAILED:
        raise UploadNotAllowed(f"An asset in {asset.status} is not failed.")

    asset.status = MediaAssetStatus.UPLOADED
    asset.error_message = ""
    asset.retry_count = 0
    asset.save(update_fields=["status", "error_message", "retry_count", "updated_at"])

    transaction.on_commit(lambda: process_media_asset.delay(str(asset.pk)))
    return asset


__all__ = [
    "REPLACEABLE",
    "NotYours",
    "UnsupportedContentType",
    "UploadNotAllowed",
    "UploadVerificationFailed",
    "complete_upload",
    "request_upload",
    "retry_processing",
]
