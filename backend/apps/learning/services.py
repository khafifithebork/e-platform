"""Recording what a learner has watched.

**Completion is defined here and nowhere else** (§10 M7, ADR-016 §2). A second
definition — in a serializer deciding what badge to show, in a query counting
finished lessons — is the trap that section names, and the two would disagree
the day the threshold moved.

The entitlement check lives in this function beside the write, for the reason
M5's playback token does: a caller that can reach the write without passing
the check is a caller that records having watched what they cannot watch, and
"the view checks first" is a promise every future view has to keep.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Lesson
from apps.entitlements.exceptions import EntitlementDenied
from apps.entitlements.resolver import resolve_access
from apps.learning.models import Enrollment, LessonProgress
from apps.media_assets.models import MediaAsset


@dataclass(frozen=True)
class Heartbeat:
    """One report from a player.

    ``position_seconds`` is where the playhead is now. ``watched_delta_seconds``
    is how much was watched since the last report — a delta rather than a
    total, because a total from a client that restarted its counter would
    silently undo accumulated progress, and a delta that arrives twice costs
    fifteen seconds rather than the whole lesson.
    """

    position_seconds: int
    watched_delta_seconds: int


def _lesson_duration(lesson: Lesson) -> int | None:
    """How long the lesson is, if anything knows yet.

    Comes from the media asset, which learns it from the provider when
    transcoding finishes. Before that it is unknown — and completion by
    watched time is not computable, so only an explicit mark can complete the
    lesson. Guessing a duration would let a lesson complete after ninety
    seconds because nothing had told us it was an hour long.
    """
    asset = MediaAsset.objects.filter(lesson=lesson).only("duration_seconds").first()
    return asset.duration_seconds if asset else None


def is_complete(*, watched_seconds: int, duration_seconds: int | None) -> bool:
    """The definition, in one place.

    Measured against **watched time**, not the furthest position reached: a
    learner who drags the scrubber to the end has heard nothing, and for
    language learning the listening is the value (ADR-016 §2).

    Unknown duration means not complete by this route. That is deliberately
    not "complete" and deliberately not an error — the learner can still mark
    it themselves.
    """
    if not duration_seconds:
        return False
    return watched_seconds >= duration_seconds * settings.LESSON_COMPLETION_THRESHOLD


@transaction.atomic
def record_progress(*, user: User, lesson: Lesson, heartbeat: Heartbeat) -> LessonProgress:
    """Fold one heartbeat into a learner's progress.

    Upserted, never appended: the unique constraint on ``(user, lesson)`` is
    what makes an hour of watching one row instead of two hundred and forty,
    and ``select_for_update`` is what stops two beats racing to write the same
    row from different tabs.
    """
    decision = resolve_access(user=user, lesson=lesson)
    if not decision.allowed:
        # Recording progress against a lesson you cannot watch is either a
        # confused client or an attempt to manufacture a completion.
        raise EntitlementDenied(decision)

    duration = _lesson_duration(lesson)

    progress, _ = LessonProgress.objects.select_for_update().get_or_create(user=user, lesson=lesson)

    # Clamped rather than trusted. A client is free to report its own watching
    # — ADR-016 §2 is explicit that this is not fraud prevention — but a beat
    # claiming ten thousand seconds is a bug in the player or a stuck tab, and
    # letting it through makes the number meaningless for everyone reading it
    # afterwards.
    delta = max(0, min(heartbeat.watched_delta_seconds, settings.PROGRESS_MAX_HEARTBEAT_SECONDS))

    progress.last_position_seconds = max(0, heartbeat.position_seconds)
    # Never moves backwards: the furthest point reached is a fact about the
    # past, and the database refuses a row where it is behind the playhead.
    progress.max_position_seconds = max(
        progress.max_position_seconds, progress.last_position_seconds
    )
    progress.watched_seconds += delta
    if duration:
        # Capped at the lesson's length. Rewatching should not accumulate
        # towards a number that is supposed to mean "how much of this have you
        # seen".
        progress.watched_seconds = min(progress.watched_seconds, duration)

    if progress.completed_at is None and is_complete(
        watched_seconds=progress.watched_seconds, duration_seconds=duration
    ):
        progress.completed_at = timezone.now()

    # `completed_at` is never cleared here. A learner who rewatches a finished
    # lesson has not unfinished it, and clearing it would make progress
    # reporting able to take away something a learner earned.
    progress.save(
        update_fields=[
            "last_position_seconds",
            "max_position_seconds",
            "watched_seconds",
            "completed_at",
            "updated_at",
        ]
    )

    _bookmark(user=user, lesson=lesson)
    return progress


@transaction.atomic
def mark_complete(*, user: User, lesson: Lesson) -> LessonProgress:
    """Let a learner say they are done.

    ADR-016 §2: somebody who already speaks the material should not have to
    sit through it, and a course a competent learner can never finish is its
    own kind of wrong.

    Idempotent, and it never moves the date. Re-marking a completed lesson
    would rewrite when it was finished, which is the one thing the field is
    for.
    """
    decision = resolve_access(user=user, lesson=lesson)
    if not decision.allowed:
        raise EntitlementDenied(decision)

    progress, _ = LessonProgress.objects.select_for_update().get_or_create(user=user, lesson=lesson)

    if progress.completed_at is None:
        progress.completed_at = timezone.now()
        progress.save(update_fields=["completed_at", "updated_at"])

    _bookmark(user=user, lesson=lesson)
    return progress


def _bookmark(*, user: User, lesson: Lesson) -> None:
    """Remember where to resume, enrolling on first contact.

    Watching a lesson is what enrolment means, so there is no separate act of
    enrolling — a learner who presses play is taking the course. That is only
    safe because an enrolment grants nothing (ADR-016 §1); if it did, this
    would be a self-service access grant.
    """
    Enrollment.objects.update_or_create(
        user=user,
        course_id=lesson.course_id,
        defaults={"last_lesson": lesson},
    )
