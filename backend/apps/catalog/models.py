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


class CourseReviewEvent(UUIDPrimaryKeyModel, TimestampedModel):
    """One step in a course's passage through review.

    Append-only. A mutable status says what is true now; it cannot answer why
    a course is live, who decided, or what they said — which is what a support
    ticket six weeks later actually asks (§5.2 makes the same argument for
    subscription events).

    Records submissions as well as decisions, which is why the fields are
    ``actor``/``action`` rather than ``reviewer``/``decision``: the actor is
    the instructor on a submission and an admin on everything else. Submission
    has to be here rather than in a ``Course.submitted_at`` column because the
    review queue orders on it — a column would be corrupted by any later edit,
    letting a typo fix jump the queue — and because the reject-fix-resubmit
    loop is history a single column cannot hold.

    Nothing downstream derives publication from this table; the state machine
    in ``services.py`` does that. The trail explains, it does not authorise.
    """

    class Action(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted for review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes requested"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="review_events")
    actor = models.ForeignKey(
        User,
        # PROTECT (§5.4): deleting an admin must not erase the record of who
        # approved what.
        on_delete=models.PROTECT,
        related_name="course_reviews",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    # Read by the instructor whose course this is — that is the point of
    # rejection notes. Not a private scratchpad: anything an admin would not
    # say to the instructor does not belong in this field.
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list] = [
            models.Index(fields=["course", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} on {self.course_id}"


class Section(UUIDPrimaryKeyModel, TimestampedModel):
    """A chapter within a course."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=200)
    position = models.PositiveIntegerField()

    class Meta:
        ordering: ClassVar[list[str]] = ["position"]
        constraints: ClassVar[list] = [
            # Deferrable, so a reorder can swap two positions inside one
            # transaction. Without DEFERRED the intermediate state — two
            # sections briefly at the same position — violates the constraint
            # mid-statement and the whole reorder fails.
            models.UniqueConstraint(
                fields=["course", "position"],
                name="section_position_unique_per_course",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]

    def __str__(self) -> str:
        return self.title


class LessonType(models.TextChoices):
    """Extensible on purpose (ADR-002 §7.5): a live session is a lesson type,
    not a boolean somewhere."""

    VIDEO = "VIDEO", "Video"
    AUDIO = "AUDIO", "Audio"
    TEXT = "TEXT", "Text"
    RESOURCE = "RESOURCE", "Resource"


class Lesson(UUIDPrimaryKeyModel, TimestampedModel):
    """A single lesson.

    Carries **both** ``section`` and ``course``. ADR-007 §1: §6.2 routes
    /courses/{slug}/lessons/{lesson_slug}/, which resolves to one lesson only
    if the slug is unique per course — and a constraint spanning two joins is
    not something Django can express. Uniqueness enforced in a service is
    uniqueness a bulk import walks straight past, so the redundant foreign key
    buys a real database guarantee (invariant 11). It also makes
    lesson-to-course one hop on the hottest read path.

    No media here. MediaAsset, duration and playback are M5.
    """

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="lessons")

    slug = models.SlugField(max_length=140)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)

    lesson_type = models.CharField(
        max_length=16, choices=LessonType.choices, default=LessonType.VIDEO
    )
    position = models.PositiveIntegerField()

    is_preview = models.BooleanField(
        default=False,
        help_text=(
            "Watchable without a subscription. The entitlement resolver reads "
            "this in M4; it grants nothing on its own."
        ),
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["position"]
        indexes: ClassVar[list] = [
            models.Index(fields=["section", "position"]),
        ]
        constraints: ClassVar[list] = [
            # The URL contract from §6.2, as a database guarantee.
            models.UniqueConstraint(
                fields=["course", "slug"], name="lesson_slug_unique_per_course"
            ),
            models.UniqueConstraint(
                fields=["section", "position"],
                name="lesson_position_unique_per_section",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]

    def __str__(self) -> str:
        return self.title
