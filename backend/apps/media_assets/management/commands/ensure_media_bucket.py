"""Create the media bucket if it is missing.

Development and CI only. In production the bucket is created once, by whoever
holds the account, with the lifecycle rules and access policy this codebase
has no business setting — so this is a convenience for `make dev`, not part of
deployment.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.media_assets.providers.storage import object_storage


class Command(BaseCommand):
    help = "Create the media bucket in the configured S3-compatible store."

    def handle(self, *args, **options) -> None:
        object_storage().ensure_bucket()
        self.stdout.write(
            self.style.SUCCESS(
                f"Bucket {settings.MEDIA_STORAGE_BUCKET} ready at {settings.MEDIA_STORAGE_ENDPOINT}"
            )
        )
