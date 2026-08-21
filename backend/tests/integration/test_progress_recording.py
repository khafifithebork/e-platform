"""Recording progress, and the one definition of "complete".

§10 M7 asks for completion to be defined precisely once and names it your
brainstorm's Trap 3. These tests are mostly about the edges of that definition
and about the write surviving a client that repeats itself.

The one worth reading twice is that **scrubbing to the end completes nothing**.
That is ADR-016 §2's whole argument: for language learning the listening is
the value, so a learner who dragged the playhead has finished nothing, and
recording otherwise would put a false achievement in the one place a learner
looks to know what they have covered.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.entitlements.exceptions import EntitlementDenied
from apps.learning.models import Enrollment, LessonProgress
from apps.learning.services import Heartbeat, mark_complete, record_progress
from apps.media_assets.models import MediaAsset, MediaAssetStatus

PASSWORD = "a-long-enough-passphrase"
DURATION = 600  # ten minutes

pytestmark = pytest.mark.django_db


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def lesson(db):
    """A published lesson whose media knows how long it is."""
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    instructor = _user("teacher@example.test", Role.INSTRUCTOR)
    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
        duration_seconds=DURATION,
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return lesson


@pytest.fixture
def learner(db):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    user = _user("learner@example.test")
    start_subscription(user=user, provider=FakeBillingProvider())
    return user


def _beat(learner, lesson, position: int, watched: int = 15):
    return record_progress(
        user=learner,
        lesson=lesson,
        heartbeat=Heartbeat(position_seconds=position, watched_delta_seconds=watched),
    )


class TestProgressIsUpserted:
    """Abuse case 5."""

    def test_a_heartbeat_creates_one_row(self, learner, lesson) -> None:
        _beat(learner, lesson, position=15)

        assert LessonProgress.objects.count() == 1

    def test_two_hundred_heartbeats_are_still_one_row(self, learner, lesson) -> None:
        """An hour of watching at fifteen-second beats. Appending instead
        would give "where did I get to" hundreds of answers."""
        for beat in range(1, 41):
            _beat(learner, lesson, position=beat * 15)

        assert LessonProgress.objects.count() == 1

    def test_the_position_is_the_latest_reported(self, learner, lesson) -> None:
        _beat(learner, lesson, position=100)
        _beat(learner, lesson, position=200)

        assert LessonProgress.objects.get().last_position_seconds == 200

    def test_watched_time_accumulates(self, learner, lesson) -> None:
        """A delta, not a total: a client that restarted its counter would
        otherwise undo everything accumulated so far."""
        _beat(learner, lesson, position=15, watched=15)
        _beat(learner, lesson, position=30, watched=15)

        assert LessonProgress.objects.get().watched_seconds == 30


class TestTheFurthestPointOnlyMovesForward:
    """Abuse case 6."""

    def test_rewinding_does_not_move_it_back(self, learner, lesson) -> None:
        _beat(learner, lesson, position=300)

        _beat(learner, lesson, position=50)

        progress = LessonProgress.objects.get()
        assert progress.last_position_seconds == 50
        assert progress.max_position_seconds == 300

    def test_a_negative_position_is_floored(self, learner, lesson) -> None:
        """The database refuses a negative, so a client sending one would
        otherwise be a 500 rather than a clamp."""
        progress = _beat(learner, lesson, position=-5)

        assert progress.last_position_seconds == 0


class TestCompletion:
    """ADR-016 §2, at its edges."""

    def test_watching_most_of_it_completes(self, learner, lesson, settings) -> None:
        settings.LESSON_COMPLETION_THRESHOLD = 0.9

        for _ in range(DURATION // 60):
            _beat(learner, lesson, position=DURATION, watched=60)

        assert LessonProgress.objects.get().completed_at is not None

    def test_just_under_the_threshold_does_not(self, learner, lesson, settings) -> None:
        """The boundary, from below. A learner who stopped a minute early has
        not finished, and telling them they have is the failure."""
        settings.LESSON_COMPLETION_THRESHOLD = 0.9
        # 480s of 600 is 80%.
        for _ in range(8):
            _beat(learner, lesson, position=480, watched=60)

        assert LessonProgress.objects.get().completed_at is None

    def test_scrubbing_to_the_end_completes_nothing(self, learner, lesson) -> None:
        """The test this milestone turns on. The playhead is at the end and
        the furthest point reached is the end — and nothing was watched, so
        nothing is complete. Measuring from max_position_seconds instead
        would mark this finished."""
        _beat(learner, lesson, position=DURATION, watched=1)

        progress = LessonProgress.objects.get()
        assert progress.max_position_seconds == DURATION
        assert progress.completed_at is None

    def test_a_learner_may_mark_it_complete(self, learner, lesson) -> None:
        """Somebody who already speaks the material should not have to sit
        through it."""
        assert mark_complete(user=learner, lesson=lesson).completed_at is not None

    def test_marking_twice_does_not_move_the_date(self, learner, lesson) -> None:
        """Re-marking would rewrite when it was finished, which is the one
        thing the field is for."""
        first = mark_complete(user=learner, lesson=lesson).completed_at

        assert mark_complete(user=learner, lesson=lesson).completed_at == first

    def test_rewatching_does_not_un_complete(self, learner, lesson) -> None:
        """Abuse case 7. Progress reporting must not be able to take away
        something a learner earned."""
        mark_complete(user=learner, lesson=lesson)

        _beat(learner, lesson, position=5, watched=5)

        assert LessonProgress.objects.get().completed_at is not None

    def test_a_lesson_of_unknown_length_never_auto_completes(self, learner, lesson) -> None:
        """Before transcoding finishes nothing knows how long the lesson is.
        Guessing would let it complete after ninety seconds because nothing
        had said it was an hour."""
        MediaAsset.objects.filter(lesson=lesson).update(duration_seconds=None)

        for _ in range(20):
            _beat(learner, lesson, position=1000, watched=60)

        assert LessonProgress.objects.get().completed_at is None

    def test_but_it_can_still_be_marked(self, learner, lesson) -> None:
        """The positive twin: unknown duration must not trap a learner."""
        MediaAsset.objects.filter(lesson=lesson).update(duration_seconds=None)

        assert mark_complete(user=learner, lesson=lesson).completed_at is not None

    def test_the_threshold_is_configuration(self, learner, lesson, settings) -> None:
        """A literal 0.9 in the service would pass the tests above by
        coincidence at the default and fail here."""
        settings.LESSON_COMPLETION_THRESHOLD = 0.5

        for _ in range(5):
            _beat(learner, lesson, position=300, watched=60)

        assert LessonProgress.objects.get().completed_at is not None


class TestAHeartbeatIsClamped:
    def test_an_absurd_delta_is_capped(self, learner, lesson, settings) -> None:
        """A stuck tab reporting hours in one beat makes watched_seconds
        meaningless for everyone who reads it afterwards."""
        settings.PROGRESS_MAX_HEARTBEAT_SECONDS = 60

        _beat(learner, lesson, position=30, watched=100_000)

        assert LessonProgress.objects.get().watched_seconds == 60

    def test_watched_time_never_exceeds_the_lesson(self, learner, lesson) -> None:
        """Rewatching should not accumulate towards a number that is supposed
        to mean "how much of this have you seen"."""
        for _ in range(30):
            _beat(learner, lesson, position=DURATION, watched=60)

        assert LessonProgress.objects.get().watched_seconds == DURATION

    def test_a_negative_delta_takes_nothing_away(self, learner, lesson) -> None:
        _beat(learner, lesson, position=100, watched=60)

        _beat(learner, lesson, position=110, watched=-1000)

        assert LessonProgress.objects.get().watched_seconds == 60


class TestEntitlementIsCheckedBesideTheWrite:
    """Abuse case 3."""

    def test_progress_for_a_lesson_you_cannot_watch_is_refused(self, lesson) -> None:
        """A caller reaching the write without passing the check records
        having watched what they cannot watch."""
        stranger = _user("broke@example.test")

        with pytest.raises(EntitlementDenied):
            _beat(stranger, lesson, position=30)

        assert not LessonProgress.objects.exists()

    def test_marking_complete_is_checked_too(self, lesson) -> None:
        """The other write, and the one that would manufacture a completion
        outright."""
        stranger = _user("broke@example.test")

        with pytest.raises(EntitlementDenied):
            mark_complete(user=stranger, lesson=lesson)

        assert not LessonProgress.objects.exists()

    def test_losing_the_subscription_stops_further_progress(self, learner, lesson) -> None:
        """Provoked in both directions with the same learner."""
        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        _beat(learner, lesson, position=30)

        cancel(
            subscription=Subscription.objects.get(user=learner),
            provider=FakeBillingProvider(),
            immediately=True,
        )

        with pytest.raises(EntitlementDenied):
            _beat(learner, lesson, position=60)

    def test_a_preview_lesson_records_progress_for_anyone(self, lesson) -> None:
        """The resolver's first branch reaches here too: a preview is
        watchable without an account, so progress against one is legitimate."""
        from apps.catalog.models import Lesson

        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)
        lesson.refresh_from_db()
        stranger = _user("curious@example.test")

        _beat(stranger, lesson, position=30)

        assert LessonProgress.objects.filter(user=stranger).exists()


class TestWatchingEnrols:
    def test_the_first_heartbeat_creates_an_enrolment(self, learner, lesson) -> None:
        """There is no separate act of enrolling: pressing play is taking the
        course. Only safe because an enrolment grants nothing (ADR-016 §1)."""
        _beat(learner, lesson, position=15)

        assert Enrollment.objects.filter(user=learner, course=lesson.course).exists()

    def test_further_heartbeats_do_not_enrol_again(self, learner, lesson) -> None:
        """The unique constraint would refuse a second, so a service that
        created rather than upserted would fail on the second beat of every
        lesson."""
        _beat(learner, lesson, position=15)
        _beat(learner, lesson, position=30)

        assert Enrollment.objects.count() == 1

    def test_the_bookmark_follows_the_learner(self, learner, lesson) -> None:
        """What "resume" reads."""
        from apps.catalog.models import Lesson

        second = Lesson.objects.create(
            course=lesson.course,
            section=lesson.section,
            slug="second",
            title="Second",
            position=2,
        )

        _beat(learner, lesson, position=15)
        _beat(learner, second, position=15)

        assert Enrollment.objects.get().last_lesson == second


class TestCompletionIsDefinedOnce:
    """§10 M7's Trap 3, guarded structurally.

    A second definition — in a serializer deciding a badge, in a query
    counting finished lessons — is what that section warns about, and the two
    would disagree the day the threshold moved. No behavioural test can see a
    definition that has not been written yet, so this reads the source.
    """

    def test_the_threshold_setting_is_read_in_one_place(self) -> None:
        from pathlib import Path

        apps_root = Path(__file__).resolve().parents[2] / "apps"
        readers = []

        for path in apps_root.rglob("*.py"):
            if "migrations" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "LESSON_COMPLETION_THRESHOLD" in source:
                readers.append(path.name)

        assert readers == ["services.py"], (
            f"completion must be defined once (§10 M7, ADR-016 §2); read in {readers}"
        )

    def test_completion_is_measured_from_watched_time(self) -> None:
        """The choice ADR-016 §2 made, asserted directly: `is_complete` takes
        watched seconds and has no way to see a position at all."""
        import inspect

        from apps.learning.services import is_complete

        parameters = set(inspect.signature(is_complete).parameters)

        assert parameters == {"watched_seconds", "duration_seconds"}
