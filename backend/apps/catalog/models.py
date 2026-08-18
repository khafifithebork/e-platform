"""The catalogue.

`architecture.md` §3 calls this product curated and admin-approved. The
``status`` field on ``Course`` is where that promise lives: everything the
public can see got there because an admin approved it, and the transitions that
enforce it are in ``services.py`` rather than scattered through views
(ADR-007 §2).
"""

from typing import ClassVar

from django.db import models

from apps.accounts.models import User
from apps.core.models import TimestampedModel, UUIDPrimaryKeyModel


class Language(TimestampedModel):
    """A language courses are taught in.

    An integer primary key, unlike most things here. §5.2 reserves UUIDs for
    identifiers that appear in URLs and could be enumerated to reveal business
    volume; the list of languages a platform teaches is public by definition
    and small enough to be a lookup table.
    """

    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="ISO 639 code, e.g. 'es'. The natural key.",
    )
    name = models.CharField(max_length=100, help_text="English name, e.g. 'Spanish'.")
    native_name = models.CharField(max_length=100, help_text="e.g. 'Español'.")
    is_active = models.BooleanField(
        default=True,
        help_text="Withdrawn languages stay for existing courses but leave the catalogue.",
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return self.name


class Level(models.TextChoices):
    """CEFR. A closed scale learners already recognise."""

    A1 = "A1", "A1 — Beginner"
    A2 = "A2", "A2 — Elementary"
    B1 = "B1", "B1 — Intermediate"
    B2 = "B2", "B2 — Upper intermediate"
    C1 = "C1", "C1 — Advanced"
    C2 = "C2", "C2 — Proficient"


class CourseStatus(models.TextChoices):
    """The publication lifecycle.

    Only an admin moves a course to PUBLISHED, and only from IN_REVIEW
    (ADR-007 §2). An instructor's sole forward move is submitting for review.
    """

    DRAFT = "DRAFT", "Draft"
    IN_REVIEW = "IN_REVIEW", "In review"
    PUBLISHED = "PUBLISHED", "Published"
    ARCHIVED = "ARCHIVED", "Archived"


class Course(UUIDPrimaryKeyModel, TimestampedModel):
    """A course, owned by one instructor.

    UUID primary key: `/courses/47` tells a competitor how many courses exist,
    and makes enumeration trivial (§5.2).
    """

    slug = models.SlugField(
        max_length=140,
        unique=True,
        help_text="The public URL. Unique across the catalogue, not per instructor.",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    language = models.ForeignKey(Language, on_delete=models.PROTECT, related_name="courses")
    level = models.CharField(max_length=2, choices=Level.choices)

    skill_areas = models.JSONField(
        default=list,
        blank=True,
        help_text="Free-form tags, e.g. ['listening', 'grammar'].",
    )

    instructor = models.ForeignKey(
        User,
        # PROTECT, not CASCADE (§5.4). Deleting a user must not silently take
        # their published courses — and every learner's progress against them —
        # with it. It forces a real deactivation flow, which is what the GDPR
        # requirement needs anyway: anonymise the person, keep the content.
        on_delete=models.PROTECT,
        related_name="courses",
    )

    status = models.CharField(
        max_length=16,
        choices=CourseStatus.choices,
        default=CourseStatus.DRAFT,
        help_text="Never writable from a request body. Changed only by services.transition.",
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when an admin approves. Null means it has never been live.",
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            # §5.3 calls this the hottest query in the application: the
            # catalogue filtered by language and level, over published rows.
            models.Index(fields=["status", "language", "level"]),
            # Most catalogue reads touch only published rows, and a partial
            # index over them stays small as drafts accumulate.
            models.Index(
                fields=["-published_at"],
                condition=models.Q(status=CourseStatus.PUBLISHED),
                name="course_published_recent",
            ),
        ]
        constraints: ClassVar[list] = [
            # A published course must have a publication date, and an
            # unpublished one must not. Without this the two can drift apart,
            # and "when did this go live" stops being answerable.
            models.CheckConstraint(
                condition=(
                    models.Q(status=CourseStatus.PUBLISHED, published_at__isnull=False)
                    | ~models.Q(status=CourseStatus.PUBLISHED)
                ),
                name="course_published_has_published_at",
            ),
        ]

    def __str__(self) -> str:
        return self.title
