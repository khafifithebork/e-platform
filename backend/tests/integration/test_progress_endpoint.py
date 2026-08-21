"""The progress endpoints, end to end.

Abuse cases 3 and 4, plus the loop the milestone is actually about: watch,
persist, resume.

Abuse case 4 — reaching another learner's progress — is worth reading for what
the test *cannot* do. There is no identifier in any of these routes for whose
progress it is, so the test has to demonstrate the absence rather than a
refusal: two learners hit the same URL and get their own rows.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.learning.models import Enrollment, LessonProgress
from apps.media_assets.models import MediaAsset, MediaAssetStatus

PASSWORD = "a-long-enough-passphrase"
DURATION = 600

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _subscribe(user):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    start_subscription(user=user, provider=FakeBillingProvider())
    return user


@pytest.fixture
def lesson(db):
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
    return _subscribe(_user("learner@example.test"))


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/progress/"


def _beat(client, lesson, position: int, watched: int = 15):
    return client.put(
        _url(lesson),
        {"position_seconds": position, "watched_delta_seconds": watched},
        content_type="application/json",
    )


class TestTheLoop:
    """Watch, persist, resume."""

    def test_a_heartbeat_is_recorded(self, client, lesson, learner) -> None:
        _sign_in(client, "learner@example.test")

        response = _beat(client, lesson, position=120)

        assert response.status_code == 200
        assert response.json()["last_position_seconds"] == 120

    def test_progress_survives_signing_out_and_back_in(self, client, lesson, learner) -> None:
        """ "Resume across devices" reduced to what a test can actually see: a
        second session reads what the first wrote."""
        _sign_in(client, "learner@example.test")
        _beat(client, lesson, position=200)
        client.post("/api/v1/auth/logout/")

        _sign_in(client, "learner@example.test")
        body = client.get(_url(lesson)).json()

        assert body["last_position_seconds"] == 200

    def test_a_lesson_never_started_answers_204(self, client, lesson, learner) -> None:
        """Distinct from a 404: a player needs to tell "you have not begun"
        from "there is no such lesson"."""
        _sign_in(client, "learner@example.test")

        assert client.get(_url(lesson)).status_code == 204

    def test_marking_complete_works_through_the_api(self, client, lesson, learner) -> None:
        _sign_in(client, "learner@example.test")

        response = client.post(f"/api/v1/lessons/{lesson.id}/complete/")

        assert response.status_code == 200
        assert response.json()["completed_at"] is not None


class TestProgressIsAlwaysYourOwn:
    """Abuse case 4."""

    def test_two_learners_at_the_same_url_get_their_own_rows(self, client, lesson, learner) -> None:
        """The strongest form of the guarantee: there is no identifier to
        tamper with, so another learner's progress is unreachable rather than
        forbidden."""
        other = _subscribe(_user("other@example.test"))

        _sign_in(client, "learner@example.test")
        _beat(client, lesson, position=300)
        client.post("/api/v1/auth/logout/")

        _sign_in(client, "other@example.test")
        assert client.get(_url(lesson)).status_code == 204

        _beat(client, lesson, position=50)

        assert LessonProgress.objects.get(user=learner).last_position_seconds == 300
        assert LessonProgress.objects.get(user=other).last_position_seconds == 50

    def test_a_user_id_in_the_body_is_ignored(self, client, lesson, learner) -> None:
        other = _subscribe(_user("other@example.test"))
        _sign_in(client, "learner@example.test")

        client.put(
            _url(lesson),
            {"position_seconds": 90, "watched_delta_seconds": 15, "user": str(other.pk)},
            content_type="application/json",
        )

        assert not LessonProgress.objects.filter(user=other).exists()

    def test_anonymous_is_refused(self, client, lesson) -> None:
        assert _beat(client, lesson, position=30).status_code in (401, 403)


class TestEntitlementReachesTheEndpoint:
    """Abuse case 3, through HTTP."""

    def test_someone_without_a_subscription_cannot_record(self, client, lesson) -> None:
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        response = _beat(client, lesson, position=30)

        assert response.status_code == 403
        assert response.json()["reason"] == "NO_SUBSCRIPTION"
        assert not LessonProgress.objects.exists()

    def test_nor_mark_complete(self, client, lesson) -> None:
        """The one that would manufacture an achievement outright."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        assert client.post(f"/api/v1/lessons/{lesson.id}/complete/").status_code == 403
        assert not LessonProgress.objects.exists()

    def test_an_unpublished_lesson_is_a_404(self, client, lesson, learner) -> None:
        """The visibility gate, ahead of entitlement as everywhere else."""
        from apps.catalog.models import Course

        Course.objects.filter(pk=lesson.course_id).update(status="DRAFT")
        _sign_in(client, "learner@example.test")

        assert _beat(client, lesson, position=30).status_code == 404


class TestWhatAClientMaySend:
    def test_watched_seconds_cannot_be_set_directly(self, client, lesson, learner) -> None:
        """A client posting the lesson's duration once would complete it
        instantly. Only a delta is accepted, and the service derives the rest."""
        _sign_in(client, "learner@example.test")

        client.put(
            _url(lesson),
            {
                "position_seconds": 30,
                "watched_delta_seconds": 15,
                "watched_seconds": DURATION,
                "completed_at": "2020-01-01T00:00:00Z",
            },
            content_type="application/json",
        )

        progress = LessonProgress.objects.get()
        assert progress.watched_seconds == 15
        assert progress.completed_at is None

    def test_a_missing_field_is_a_400(self, client, lesson, learner) -> None:
        _sign_in(client, "learner@example.test")

        response = client.put(
            _url(lesson), {"position_seconds": 30}, content_type="application/json"
        )

        assert response.status_code == 400

    def test_an_absurd_delta_is_rejected_loudly(self, client, lesson, learner) -> None:
        """The serializer refuses nonsense with a 400; the service clamps
        quietly, because it is also reachable from code that is not a
        request."""
        _sign_in(client, "learner@example.test")

        response = _beat(client, lesson, position=30, watched=100_000)

        assert response.status_code == 400

    def test_the_serializer_exposes_nothing_writable(self) -> None:
        """ADR-011: every field that decides something is read-only."""
        from apps.learning.serializers import LessonProgressSerializer

        writable = {
            name for name, field in LessonProgressSerializer().fields.items() if not field.read_only
        }

        assert writable == set()


class TestWatchingEnrolsThroughTheApi:
    def test_a_first_heartbeat_enrols(self, client, lesson, learner) -> None:
        _sign_in(client, "learner@example.test")

        _beat(client, lesson, position=15)

        assert Enrollment.objects.filter(user=learner, course=lesson.course).exists()

    def test_a_refused_heartbeat_enrols_nobody(self, client, lesson) -> None:
        """The enrolment is written after the entitlement check, so a refusal
        must leave no trace — otherwise "my courses" fills with courses
        somebody was never allowed to watch."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        _beat(client, lesson, position=15)

        assert not Enrollment.objects.exists()


class TestQueryCost:
    def test_a_heartbeat_costs_a_fixed_number_of_queries(
        self, client, lesson, learner, django_assert_num_queries
    ) -> None:
        """ADR-009. This runs every ten to fifteen seconds per open lesson,
        which makes it the highest-frequency authenticated write in the
        product.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _sign_in(client, "learner@example.test")
        # Primed, so the count reflects the steady state rather than first
        # contact: a player beats hundreds of times and creates once.
        _beat(client, lesson, position=15)

        with CaptureQueriesContext(connection) as captured:
            _beat(client, lesson, position=30)

        # Savepoints filtered out: pytest-django wraps each test in a
        # transaction, so `transaction.atomic` becomes a savepoint pair that
        # production does not pay for.
        real = [
            query for query in captured.captured_queries if "SAVEPOINT" not in query["sql"].upper()
        ]

        # Session, user, the lesson, the resolver's two checks, the media
        # duration, the progress row and its update, and reading the bookmark.
        # The bookmark is *not* rewritten, because it has not moved — that is
        # the one query removed after measuring rather than pinning.
        assert len(real) == 9, [query["sql"][:90] for query in real]

    def test_the_bookmark_is_only_written_when_it_moves(self, client, lesson, learner) -> None:
        """The steady state of watching one lesson is hundreds of beats and no
        bookmark change. Rewriting it each time is a write per beat to store
        what was already there."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _sign_in(client, "learner@example.test")
        _beat(client, lesson, position=15)

        with CaptureQueriesContext(connection) as captured:
            _beat(client, lesson, position=30)

        writes = [
            query
            for query in captured.captured_queries
            if "learning_enrollment" in query["sql"]
            and query["sql"].strip().upper().startswith("UPDATE")
        ]

        assert writes == []

    def test_but_it_is_written_when_the_learner_moves_on(self, client, lesson, learner) -> None:
        """The positive twin. A bookmark that never updated would satisfy the
        test above and leave "resume" pointing at the first lesson forever."""
        from apps.catalog.models import Lesson

        second = Lesson.objects.create(
            course=lesson.course,
            section=lesson.section,
            slug="second",
            title="Second",
            position=2,
        )
        _sign_in(client, "learner@example.test")
        _beat(client, lesson, position=15)

        _beat(client, second, position=15)

        assert Enrollment.objects.get(user=learner).last_lesson == second
