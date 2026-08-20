"""Transcripts as structured rows — invariant 13.

VTT is a rendered, cached projection and never the stored form. §5.2 gives
four reasons and each is a capability that would be lost by storing caption
files: the review UI is CRUD instead of file parsing, "click a line, seek the
video" is a ``start_ms`` lookup, a translation is a second ``Transcript``
against the same asset rather than a second file, and full-text search over
lesson *content* stays possible.

The provider is one opaque string plus a job id, the same pattern as billing
in M4 and video in M5. Nothing here models Deepgram, which has not been signed
up for (ADR-014 §1).
"""

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.catalog.models import Language
from apps.core.models import TimestampedModel, UUIDPrimaryKeyModel
from apps.media_assets.models import MediaAsset


class TranscriptKind(models.TextChoices):
    """What this transcript *is*.

    A translation is a second row against the same asset — §5.2's argument for
    rows over files, made concrete. Modelled now and produced in a later
    milestone: translating needs a second provider and a second bill.
    """

    TARGET = "TARGET", "In the language being taught"
    TRANSLATION = "TRANSLATION", "Translated for the learner"


class TranscriptStatus(models.TextChoices):
    PENDING = "PENDING", "Not yet transcribed"
    MACHINE = "MACHINE", "Machine output, unreviewed"
    IN_REVIEW = "IN_REVIEW", "Being reviewed"
    APPROVED = "APPROVED", "Reviewed and approved"
    FAILED = "FAILED", "Transcription failed"


class Transcript(UUIDPrimaryKeyModel, TimestampedModel):
    """One transcription of one media asset, in one language.

    ``APPROVED`` is the only status a learner ever sees rendered (ADR-014 §3).
    That decision put the whole weight of "unreviewed subtitles are worse than
    none" on readers honouring this field, so anything that renders segments
    must check it — not only the VTT endpoint that checked it first.
    """

    media_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name="transcripts",
    )
    language = models.ForeignKey(
        Language,
        # PROTECT (§5.4): removing a language must not silently delete the
        # transcripts written in it.
        on_delete=models.PROTECT,
        related_name="transcripts",
    )

    kind = models.CharField(
        max_length=16, choices=TranscriptKind.choices, default=TranscriptKind.TARGET
    )
    status = models.CharField(
        max_length=16, choices=TranscriptStatus.choices, default=TranscriptStatus.PENDING
    )

    provider = models.CharField(
        max_length=32,
        blank=True,
        help_text="Which system produced this. Empty until one has.",
    )
    # NULL rather than "" against ruff's DJ001, and for the same reason as
    # M4's provider_subscription_id: PostgreSQL treats NULLs as distinct, so
    # every not-yet-submitted transcript can coexist under the unique
    # constraint below. With "" the second one would be refused.
    provider_job_id = models.CharField(  # noqa: DJ001
        max_length=128,
        null=True,
        blank=True,
        help_text="The provider's handle for the job. How a callback finds this row.",
    )

    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Provider's own score, 0 to 1. Null until it has run.",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transcripts_reviewed",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # The dead-letter queue, same shape as MediaAsset's. §10 M5 named
    # "failures vanish silently" as a mistake to avoid, and a FAILED
    # transcript with no reason is that mistake wearing a different status:
    # nobody can list what broke, count it for an alert, or decide whether
    # retrying is worth it.
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            # The VTT endpoint's question: the approved transcript for this
            # asset in this language.
            models.Index(fields=["media_asset", "language", "status"]),
        ]
        constraints: ClassVar[list] = [
            # Two transcripts of the same kind in the same language are two
            # answers to one question, and the renderer would have to pick.
            models.UniqueConstraint(
                fields=["media_asset", "language", "kind"],
                name="transcript_unique_per_language_and_kind",
            ),
            # A callback matching two rows would apply one provider result to
            # somebody else's lesson.
            models.UniqueConstraint(
                fields=["provider", "provider_job_id"],
                name="transcript_unique_per_provider_job",
            ),
            # ADR-014 §4: the instructor approves, so an approval names them
            # and says when. An approval nobody signed is the audit gap M3's
            # review trail exists to close.
            models.CheckConstraint(
                condition=~models.Q(status=TranscriptStatus.APPROVED)
                | (models.Q(reviewed_by__isnull=False) & models.Q(approved_at__isnull=False)),
                name="approved_transcript_is_signed",
            ),
            # A provider reporting 95 rather than 0.95 would otherwise be
            # stored and read as certainty by whatever surfaces it in review.
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True)
                | models.Q(confidence__gte=0, confidence__lte=1),
                name="confidence_is_a_proportion",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} transcript ({self.status}) for {self.media_asset_id}"


class TranscriptSegment(UUIDPrimaryKeyModel, TimestampedModel):
    """One cue: a span of time and the words spoken in it.

    The unit invariant 13 is about. A VTT file is these rows rendered in
    order; a caption file on disk is these rows with the structure thrown
    away.
    """

    transcript = models.ForeignKey(
        Transcript,
        # CASCADE, unlike most relations here: a segment without a transcript
        # is orphaned text nothing can render, scope or attribute.
        on_delete=models.CASCADE,
        related_name="segments",
    )

    position = models.PositiveIntegerField()
    start_ms = models.IntegerField()
    end_ms = models.IntegerField()
    text = models.TextField()

    is_edited = models.BooleanField(
        default=False,
        help_text="A human changed this. Set on edit and never cleared.",
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["position"]
        indexes: ClassVar[list] = [
            # §5.3: ordered render, and the lookup behind "click a line, seek
            # the video".
            models.Index(fields=["transcript", "position"]),
        ]
        constraints: ClassVar[list] = [
            # Deferrable, and load-bearing: splitting a cue in review
            # renumbers everything after it, and that renumbering passes
            # through a duplicate position. ADR-009 §5 — the paired IMMEDIATE
            # test is what proves the deferral is real, since nothing commits
            # under pytest-django.
            models.UniqueConstraint(
                fields=["transcript", "position"],
                name="segment_position_unique_per_transcript",
                deferrable=models.Deferrable.DEFERRED,
            ),
            # A cue with no duration renders as a subtitle that never appears.
            models.CheckConstraint(
                condition=models.Q(end_ms__gt=models.F("start_ms")),
                name="segment_ends_after_it_starts",
            ),
            # Before the media begins: a VTT timestamp cannot express it, and
            # a player's behaviour on one is anybody's guess.
            models.CheckConstraint(
                condition=models.Q(start_ms__gte=0),
                name="segment_starts_within_the_media",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.start_ms}-{self.end_ms}] {self.text[:40]}"
