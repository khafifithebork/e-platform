"""Query counts on every list endpoint. Abuse case 9.

The usual form of this test — ``assert_num_queries(3)`` over a fixture with one
row — proves a number and nothing else. It passes just as happily when the
endpoint fans out, because with one row a fan-out costs one query. So every
test here runs the same endpoint over a small dataset and a larger one and
asserts the count is **identical**, then pins the absolute value. The first
assertion is the one that means "does not fan out"; the second stops the
number drifting upwards unnoticed.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _instructor(email: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


def _admin(email: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def course(db):
    from apps.catalog.models import Course, Language

    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    return Course.objects.create(
        slug="course",
        title="Course",
        language=language,
        level="A1",
        instructor=_instructor("me@example.test"),
    )


@pytest.fixture
def signed_in(client, course):
    client.post(
        "/api/v1/auth/login/",
        {"email": "me@example.test", "password": PASSWORD},
        content_type="application/json",
    )
    return client


def _count_queries(client, url: str) -> int:
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return len(captured)


def _assert_flat(client, url: str, *, seed, expected: int) -> None:
    """Same endpoint, two dataset sizes, same query count.

    ``seed(n)`` adds n more rows. If the endpoint fans out, the second count
    exceeds the first and the difference names how badly.
    """
    seed(1)
    small = _count_queries(client, url)

    seed(9)
    large = _count_queries(client, url)

    assert small == large, f"{url} fans out: {small} queries for 1 row, {large} for 10"
    assert large == expected, f"{url} now costs {large} queries, expected {expected}"


class TestInstructorLists:
    def test_sections(self, signed_in, course) -> None:
        from apps.catalog.models import Section

        position = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(position)
                Section.objects.create(course=course, title=f"S{index}", position=index)

        # Session, user, the course ownership check, the page itself.
        _assert_flat(
            signed_in,
            f"/api/v1/instructor/courses/{course.id}/sections/",
            seed=seed,
            expected=4,
        )

    def test_lessons(self, signed_in, course) -> None:
        from apps.catalog.models import Lesson, Section

        section = Section.objects.create(course=course, title="Only", position=1)
        position = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(position)
                Lesson.objects.create(
                    course=course,
                    section=section,
                    slug=f"lesson-{index}",
                    title=f"Lesson {index}",
                    position=index,
                )

        _assert_flat(
            signed_in,
            f"/api/v1/instructor/courses/{course.id}/lessons/",
            seed=seed,
            expected=4,
        )

    def test_review_events(self, signed_in, course) -> None:
        """Each row renders the actor's email, which is a join or a query per
        row — the clearest fan-out risk in the instructor API."""
        from apps.catalog.models import CourseReviewEvent

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                # A distinct actor per row: a shared one would be cached by
                # Django's identity map and hide a fan-out.
                CourseReviewEvent.objects.create(
                    course=course,
                    actor=_admin(f"admin-{index}@example.test"),
                    action=CourseReviewEvent.Action.SUBMITTED,
                )

        _assert_flat(
            signed_in,
            f"/api/v1/instructor/courses/{course.id}/review-events/",
            seed=seed,
            expected=4,
        )

    def test_courses(self, signed_in, course) -> None:
        """Already pinned in T4; repeated here so every list endpoint is
        covered in one place and a new one is obviously missing."""
        from apps.catalog.models import Course

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                Course.objects.create(
                    slug=f"extra-{index}",
                    title=f"Extra {index}",
                    language=course.language,
                    level="A1",
                    instructor=_instructor(f"other-{index}@example.test"),
                )

        _assert_flat(signed_in, "/api/v1/instructor/courses/", seed=seed, expected=3)


class TestPublicLists:
    def _publish(self, course) -> None:
        from apps.catalog.services import approve, submit_for_review

        submit_for_review(course=course, by=course.instructor)
        approve(course=course, by=_admin(f"approver-{course.slug}@example.test"))

    def test_catalogue(self, client, course) -> None:
        from apps.catalog.models import Course

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                extra = Course.objects.create(
                    slug=f"extra-{index}",
                    title=f"Extra {index}",
                    language=course.language,
                    level="A1",
                    # A distinct instructor per card, so a missing join shows.
                    instructor=_instructor(f"other-{index}@example.test"),
                )
                self._publish(extra)

        # One. Cursor pagination issues no COUNT, and the view declares no
        # authentication classes, so there is no session or user lookup.
        _assert_flat(client, "/api/v1/catalogue/courses/", seed=seed, expected=1)

    def test_languages(self, client, course) -> None:
        from apps.catalog.models import Course, Language

        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(counter)
                language = Language.objects.create(
                    code=f"l{index}", name=f"Language {index}", native_name=f"L{index}"
                )
                extra = Course.objects.create(
                    slug=f"extra-{index}",
                    title=f"Extra {index}",
                    language=language,
                    level="A1",
                    instructor=_instructor(f"other-{index}@example.test"),
                )
                self._publish(extra)

        _assert_flat(client, "/api/v1/catalogue/languages/", seed=seed, expected=1)


class TestLearningReads:
    """M7's reads, held to the same rule.

    "My courses" is the one that would fan out invisibly: the lesson counts and
    "what to play next" are per-enrolment questions, and answering them in
    Python is one query per course. Provoked — dropping the join reports 4
    queries for one course and 13 for ten.

    The transcript panel is here for a weaker reason, stated rather than
    implied: a reverse foreign key collection is one query however many cues
    it holds, so this endpoint is flat by construction and removing its
    prefetch does not fail this test. It is pinned anyway because serializing
    per cue is a real way to fan out later, and because the absolute number
    catches a gate or a join creeping in.
    """

    @staticmethod
    def _published_lesson(slug: str = "spanish"):
        from apps.catalog.models import Course, Language, Lesson, Section
        from apps.catalog.services import approve, submit_for_review

        instructor = _instructor(f"teacher-{slug}@example.test")
        admin = _admin(f"approver-{slug}@example.test")
        language, _ = Language.objects.get_or_create(
            code=f"x{slug[:1]}", defaults={"name": slug, "native_name": slug}
        )
        course = Course.objects.create(
            slug=slug, title=slug.title(), language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="Part", position=1)
        lesson = Lesson.objects.create(
            course=course, section=section, slug=f"{slug}-1", title="Lesson", position=1
        )
        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin)
        return lesson

    @staticmethod
    def _entitled(client, email: str = "learner@example.test"):
        from apps.accounts.services import create_account
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        learner = create_account(email=email, password=PASSWORD)
        start_subscription(user=learner, provider=FakeBillingProvider())
        client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": PASSWORD},
            content_type="application/json",
        )
        return learner

    def test_my_courses(self, client, db) -> None:
        from apps.learning.services import Heartbeat, record_progress

        learner = self._entitled(client)
        counter = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                lesson = self._published_lesson(f"course{next(counter)}")
                record_progress(user=learner, lesson=lesson, heartbeat=Heartbeat(15, 15))

        # Session, user, and the annotated page. The counts, the last activity
        # and the next lesson all ride on that one query — doing any of them in
        # Python is a query per course.
        _assert_flat(client, "/api/v1/me/courses/", seed=seed, expected=3)

    def test_the_transcript_panel(self, client, db) -> None:
        from django.utils import timezone

        from apps.media_assets.models import MediaAsset, MediaAssetStatus
        from apps.transcripts.models import (
            Transcript,
            TranscriptKind,
            TranscriptSegment,
            TranscriptStatus,
        )

        lesson = self._published_lesson()
        MediaAsset.objects.create(
            lesson=lesson,
            source_object_key="masters/abc/def.mp4",
            source_bytes=2048,
            provider="fake",
            provider_asset_id="fakeasset_abc",
            provider_playback_id="fakeplay_abc",
            status=MediaAssetStatus.READY,
            duration_seconds=600,
        )
        admin = _admin("panel-approver@example.test")
        transcript = Transcript.objects.create(
            media_asset=lesson.media_asset,
            language=lesson.course.language,
            kind=TranscriptKind.TARGET,
            status=TranscriptStatus.APPROVED,
            provider="fake",
            provider_job_id="job-counts",
            reviewed_by=admin,
            approved_at=timezone.now(),
        )
        self._entitled(client)
        position = iter(range(1, 500))

        def seed(count: int) -> None:
            TranscriptSegment.objects.bulk_create(
                TranscriptSegment(
                    transcript=transcript,
                    position=(index := next(position)),
                    start_ms=index * 1000,
                    end_ms=index * 1000 + 900,
                    text=f"linea {index}",
                )
                for _ in range(count)
            )

        # Session, user, the lesson, the resolver's two checks, the transcript
        # with its language joined, and one for the cues — one, not one each.
        _assert_flat(client, f"/api/v1/lessons/{lesson.id}/transcript/", seed=seed, expected=7)


class TestAdminDiagnostics:
    """The support endpoint, which reads five collections for one account.

    ADR-009's reason for pinning it: a per-row query here is fast until the
    account being diagnosed is the one with two years of history, which is
    exactly the account somebody opens this page for.
    """

    @pytest.fixture
    def subject(self, db):
        from apps.accounts.services import create_account

        return create_account(email="subject@example.test", password=PASSWORD)

    @pytest.fixture
    def as_admin(self, client, db):
        _admin("admin@example.test")
        client.post(
            "/api/v1/auth/login/",
            {"email": "admin@example.test", "password": PASSWORD},
            content_type="application/json",
        )
        return client

    def test_the_administrative_trail(self, as_admin, subject) -> None:
        """What this pins is flatness, and only flatness.

        It does **not** pin the absence of a join: `select_related("actor")`
        was added on purpose and every test here still passed, because a join
        changes one query's shape rather than the count. The argument against
        it lives in `core/selectors.py` and is not a performance one.

        What this would catch is a serializer rendering `actor.email` instead
        of `actor_label` — that is a query per row, and the difference between
        the two dataset sizes names it.
        """
        from apps.accounts.models import User
        from apps.entitlements.services import grant_access_override

        admin = User.objects.get(email="admin@example.test")
        grants = iter(range(1, 100))

        def seed(count: int) -> None:
            for _ in range(count):
                index = next(grants)
                grant_access_override(actor=admin, user=subject, days=1, reason=f"Grant {index}")

        # Session, user, the user being diagnosed, the resolver's override
        # check, the three diagnostic lists, then the trail and its total.
        #
        # Nine, where `test_it_does_not_fan_out_over_the_event_log` measures
        # ten on the same endpoint — and the difference is the resolver, not
        # the trail. Seeding overrides grants this subject access, so
        # `resolve_account_access` answers on the override and never reaches
        # its subscription query. Measured rather than assumed, which is the
        # whole of ADR-009.
        _assert_flat(
            as_admin,
            f"/api/v1/admin-api/users/{subject.id}/diagnostics/",
            seed=seed,
            expected=9,
        )
