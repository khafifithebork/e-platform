"""Enrolment and progress — what a learner has done, never what they may do.

**ADR-016 §1 is the thing to keep in mind reading this file.** An
``Enrollment`` is a progress container and a bookmark. It never appears in an
access decision, and `resolve_access` does not import anything from here.

The rule it prevents is tempting because it sounds ordinary: *"you must be
enrolled to watch"*. It is a second entitlement implementation, and the two
disagree the first time a subscription lapses while the enrolment row survives
— which it does by design, because it holds the learner's progress.
"""

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.catalog.models import Course, Lesson
from apps.core.models import TimestampedModel, UUIDPrimaryKeyModel


class Enrollment(UUIDPrimaryKeyModel, TimestampedModel):
    """One learner's relationship with one course.

    Carries no access meaning whatsoever. Deleting it loses a bookmark and a
    completion date; it does not take anything away that a subscription grants.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    course = models.ForeignKey(
        Course,
        # PROTECT (§5.4): removing a course while people are partway through
        # it should be a deliberate migration, not a side effect. Courses are
        # archived rather than deleted anyway (M3).
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    last_lesson = models.ForeignKey(
        Lesson,
        # SET_NULL, not CASCADE: a bookmark pointing at a removed lesson is
        # meaningless, but the enrolment and the progress behind it are not,
        # and CASCADE would take a learner's whole course history with one
        # deleted lesson.
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Where to resume. A bookmark, not a permission.",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        constraints: ClassVar[list] = [
            # Two enrolments are two sets of progress for one course, and
            # "resume" would have to choose between them.
            models.UniqueConstraint(
                fields=["user", "course"],
                name="one_enrollment_per_course",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.course_id}"


class LessonProgress(UUIDPrimaryKeyModel, TimestampedModel):
    """How far one learner has got through one lesson.

    Three numbers, and the difference between two of them is a product
    decision (ADR-016 §2):

    ``last_position_seconds`` is where the playhead is — what "resume" seeks
    to. ``max_position_seconds`` is the furthest point ever reached, which is
    set by *dragging the scrubber*. ``watched_seconds`` is time actually spent
    watching, and it is the one completion is measured against, because a
    learner who scrubbed to the end heard nothing.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesson_progress",
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="progress",
    )

    last_position_seconds = models.PositiveIntegerField(default=0)
    max_position_seconds = models.PositiveIntegerField(default=0)
    watched_seconds = models.PositiveIntegerField(default=0)

    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-updated_at"]
        indexes: ClassVar[list] = [
            # §5.3's "resume learning": the most recently touched lessons for
            # one person, which is the first thing a returning learner sees.
            models.Index(fields=["user", "-updated_at"]),
        ]
        constraints: ClassVar[list] = [
            # §5.3 calls this correctness rather than speed. A progress
            # heartbeat is a write every fifteen seconds from a client that
            # may retry: without this, an hour of watching is two hundred and
            # forty rows and "where did I get to" has no single answer.
            models.UniqueConstraint(
                fields=["user", "lesson"],
                name="one_progress_row_per_lesson",
            ),
            # There are deliberately no explicit non-negative constraints.
            # `PositiveIntegerField` already emits a database check per
            # column, which is created first and refuses the row before ours
            # would be reached — two constraints where one can never be the
            # one that fires is dead weight reading as protection. The tests
            # assert Django's checks by name instead.
            #
            # This one Django does not generate, and it encodes what the
            # column names only imply. Without it, rewatching from the start
            # would quietly rewrite how far somebody had got — and since
            # completion is measured from watched time, a learner could lose a
            # completion by pressing play again.
            #
            # Greater-than-or-equal, not strict: rewinding is ordinary, and a
            # learner who has never rewound has the two equal.
            models.CheckConstraint(
                condition=models.Q(max_position_seconds__gte=models.F("last_position_seconds")),
                name="max_position_is_at_least_last",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} at {self.last_position_seconds}s of {self.lesson_id}"
