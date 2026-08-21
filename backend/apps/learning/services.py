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


def course_is_complete(*, user: User, course_id) -> bool:
    """Every lesson finished. The rule, in one place.

    **All of them, not a proportion.** A second threshold beside
    ``LESSON_COMPLETION_THRESHOLD`` would be a second number to guess and a
    second thing to disagree about, and it is unnecessary here: a learner who
    considers an optional lesson skippable can mark it complete themselves
    (ADR-016 §2). One rule, with an override already built in, beats two
    thresholds.

    A course with no lessons is never complete. Without that guard, zero of
    zero is "all of them" and an empty course completes the instant somebody
    is enrolled in it.

    Two counts rather than one filtered aggregate. The aggregate would join
    lessons to every learner's progress and need ``distinct`` to stay right —
    the trap ``courses_in_progress`` documents. This decides whether somebody
    finished a course, it runs only on the rare transition that can change the
    answer, and obviously-correct is worth more here than one fewer round trip.
    """
    total = Lesson.objects.filter(course_id=course_id).count()

    if not total:
        return False

    finished = LessonProgress.objects.filter(
        user=user, lesson__course_id=course_id, completed_at__isnull=False
    ).count()
    return finished >= total


def _complete_course_if_finished(*, user: User, enrollment: Enrollment) -> None:
    """Set ``Enrollment.completed_at`` the moment the last lesson lands.

    **Never cleared, and never recomputed afterwards.** An instructor who adds
    a lesson to a course does not un-finish everyone who completed it — the
    same principle that stops rewatching a lesson unfinishing it, applied one
    level up. The visible consequence is a course showing four of five lessons
    complete *and* a completion date, and that is the honest reading: they
    finished the course as it stood.

    Checked only when a lesson has just completed, because that is the only
    event that can make the answer change from no to yes. Running it on every
    heartbeat would put two counting queries on the highest-frequency write in
    the product to re-answer a question whose inputs had not moved.
    """
    if enrollment.completed_at is not None:
        return

    if not course_is_complete(user=user, course_id=enrollment.course_id):
        return

    enrollment.completed_at = timezone.now()
    enrollment.save(update_fields=["completed_at", "updated_at"])


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

    just_finished_the_lesson = False
    if progress.completed_at is None and is_complete(
        watched_seconds=progress.watched_seconds, duration_seconds=duration
    ):
        progress.completed_at = timezone.now()
        just_finished_the_lesson = True

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

    enrollment = _bookmark(user=user, lesson=lesson)
    if just_finished_the_lesson:
        _complete_course_if_finished(user=user, enrollment=enrollment)
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

    just_finished_the_lesson = progress.completed_at is None
    if just_finished_the_lesson:
        progress.completed_at = timezone.now()
        progress.save(update_fields=["completed_at", "updated_at"])

    enrollment = _bookmark(user=user, lesson=lesson)
    if just_finished_the_lesson:
        _complete_course_if_finished(user=user, enrollment=enrollment)
    return progress


def _bookmark(*, user: User, lesson: Lesson) -> Enrollment:
    """Remember where to resume, enrolling on first contact.

    Watching a lesson is what enrolment means, so there is no separate act of
    enrolling — a learner who presses play is taking the course. That is only
    safe because an enrolment grants nothing (ADR-016 §1); if it did, this
    would be a self-service access grant.
    """
    enrollment = Enrollment.objects.filter(user=user, course_id=lesson.course_id).first()

    if enrollment is None:
        return Enrollment.objects.create(user=user, course_id=lesson.course_id, last_lesson=lesson)

    if enrollment.last_lesson_id == lesson.pk:
        # Written only when it moves. `update_or_create` rewrote the same
        # value on every beat — a write every fifteen seconds per learner per
        # open lesson, to store what was already there, plus the row churn of
        # a fresh `updated_at`. This is the highest-frequency write in the
        # product, so the one that is usually unnecessary is worth removing.
        return enrollment

    # `updated_at` set by hand because `.update()` bypasses `auto_now`. The row
    # genuinely changed, and a timestamp that disagrees is the sort of thing
    # somebody later trusts.
    Enrollment.objects.filter(pk=enrollment.pk).update(
        last_lesson=lesson, updated_at=timezone.now()
    )
    enrollment.last_lesson = lesson
    return enrollment
