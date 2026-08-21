"""ADR-014 §3, both halves.

That decision replaced §10 M6's publish gate with a serving gate, and it is
the only place in this project where a stated requirement is met somewhere
other than where the document put it. So both halves are proven here rather
than assumed:

**Publication is never blocked.** M3's `approve()` is untouched, and a course
whose transcripts are still being typed can go live and teach.

**Unapproved words reach no learner, by any route.** ADR-014 §3 named the risk
that comes with concentrating a requirement on one reader — anything that
later renders segments must apply the same check. A sweep across every
learner-reachable endpoint proves the current readers, and a structural guard
makes the next one hard to add by accident.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.transcripts.models import Transcript, TranscriptSegment, TranscriptStatus

PASSWORD = "a-long-enough-passphrase"
# Distinctive enough that finding it anywhere in a response body is proof, and
# plausible enough to be what a machine actually produces.
MACHINE_WORDS = "Creo que dijo beber pero quizas dijo vivir."

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


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test", Role.INSTRUCTOR)


@pytest.fixture
def course_and_lesson(db, instructor):
    """A course ready to publish, whose transcript is unreviewed machine output."""
    from apps.catalog.models import Course, Language, Lesson, Section

    language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    asset = MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
    )
    transcript = Transcript.objects.create(
        media_asset=asset,
        language=language,
        provider="fake",
        provider_job_id="fakejob_abc",
        status=TranscriptStatus.MACHINE,
    )
    TranscriptSegment.objects.create(
        transcript=transcript, position=1, start_ms=0, end_ms=1500, text=MACHINE_WORDS
    )
    return course, lesson


def _publish(course, instructor):
    from apps.catalog.services import approve, submit_for_review

    admin = _user("approver@example.test", Role.ADMIN)
    submit_for_review(course=course, by=instructor)
    return approve(course=course, by=admin)


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


class TestPublicationIsNeverBlocked:
    """The half that declines §10 M6's publish gate."""

    def test_a_course_with_an_unreviewed_transcript_still_publishes(
        self, course_and_lesson, instructor
    ) -> None:
        """A gate would block a perfectly good course whose subtitles are
        still being typed. The video was never the problem."""
        course, _ = course_and_lesson

        published = _publish(course, instructor)

        assert published.status == "PUBLISHED"

    def test_a_course_with_no_transcript_at_all_publishes(
        self, course_and_lesson, instructor
    ) -> None:
        """M3's tests publish courses with no media whatsoever, and they stay
        valid — which is what "M3 is untouched" has to mean concretely."""
        course, _ = course_and_lesson
        Transcript.objects.all().delete()

        assert _publish(course, instructor).status == "PUBLISHED"

    def test_publishing_asks_nothing_about_transcripts(self) -> None:
        """Structural, so the gate cannot be added back without the decision
        being revisited: catalog's publication service does not know
        transcripts exist."""
        source = (
            Path(__file__).resolve().parents[2] / "apps" / "catalog" / "services.py"
        ).read_text(encoding="utf-8")

        assert "transcript" not in source.lower()


class TestUnapprovedWordsReachNoLearner:
    """The half that carries the requirement instead."""

    def _learner_readable_paths(self, course, lesson) -> list[str]:
        return [
            "/api/v1/catalogue/courses/",
            f"/api/v1/catalogue/courses/{course.slug}/",
            f"/api/v1/lessons/{lesson.id}/",
            f"/api/v1/lessons/{lesson.id}/transcript.vtt",
            "/api/v1/auth/me/",
        ]

    def test_no_endpoint_serves_machine_words_to_a_subscriber(
        self, client, course_and_lesson, instructor
    ) -> None:
        """The sweep. Spot-checking the endpoint you thought of is how the
        next one leaks — this project shipped that failure once already, in
        M4, through a list route nobody had considered."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        course, lesson = course_and_lesson
        _publish(course, instructor)
        subscriber = _user("payer@example.test")
        start_subscription(user=subscriber, provider=FakeBillingProvider())
        _sign_in(client, "payer@example.test")

        for path in self._learner_readable_paths(course, lesson):
            assert MACHINE_WORDS.encode() not in client.get(path).content, path

    def test_nor_to_an_anonymous_visitor(self, client, course_and_lesson, instructor) -> None:
        course, lesson = course_and_lesson
        _publish(course, instructor)

        for path in self._learner_readable_paths(course, lesson):
            assert MACHINE_WORDS.encode() not in client.get(path).content, path

    def test_nor_when_the_lesson_is_a_free_preview(
        self, client, course_and_lesson, instructor
    ) -> None:
        """The case most likely to be missed: a preview lesson is readable by
        anyone, so an unapproved transcript on one would be public."""
        from apps.catalog.models import Lesson

        course, lesson = course_and_lesson
        _publish(course, instructor)
        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)

        for path in self._learner_readable_paths(course, lesson):
            assert MACHINE_WORDS.encode() not in client.get(path).content, path

    def test_the_reviewer_can_still_see_them(self, client, course_and_lesson, instructor) -> None:
        """The positive twin, and it matters more than usual here: a sweep
        finding the words nowhere would also pass if review had stopped
        working entirely, and nobody could correct anything."""
        _, lesson = course_and_lesson
        transcript = Transcript.objects.get(media_asset__lesson=lesson)
        _sign_in(client, "teacher@example.test")

        response = client.get(f"/api/v1/transcripts/{transcript.id}/")

        assert MACHINE_WORDS in response.json()["segments"][0]["text"]

    def test_approving_makes_them_public(self, client, course_and_lesson, instructor) -> None:
        """The other direction. Without this the whole feature could be
        "never serve anything" and every test above would pass."""
        course, lesson = course_and_lesson
        _publish(course, instructor)
        Transcript.objects.filter(media_asset__lesson=lesson).update(
            status=TranscriptStatus.APPROVED,
            reviewed_by=instructor,
            approved_at=timezone.now(),
        )
        from apps.catalog.models import Lesson

        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)

        body = client.get(f"/api/v1/lessons/{lesson.id}/transcript.vtt").content

        assert MACHINE_WORDS.encode() in body


class TestTheNextReaderCannotForget:
    """ADR-014 §3 named this risk explicitly.

    Concentrating the requirement on one reader means every later reader must
    apply the same check, and no behavioural test can see a reader that does
    not exist yet. So this is structural: nothing outside the transcripts app
    may touch segments at all, which forces a future interactive transcript,
    search result or export to come through the app where the approved-only
    selector lives.

    It does not stop somebody writing a second unfiltered query *inside* the
    app — that is what the sweep above is for, and what a reviewer reading
    ADR-014 §3 is for.
    """

    def _modules_outside_transcripts(self):
        apps_root = Path(__file__).resolve().parents[2] / "apps"
        for path in apps_root.rglob("*.py"):
            parts = path.parts
            if "transcripts" in parts or "migrations" in parts:
                continue
            yield path

    def test_no_app_outside_transcripts_imports_segments(self) -> None:
        offenders = []
        for path in self._modules_outside_transcripts():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and "transcripts.models" in node.module
                ):
                    names = {alias.name for alias in node.names}
                    if names & {"TranscriptSegment", "Transcript"}:
                        offenders.append(f"{path.name}: {sorted(names)}")

        assert not offenders, (
            "Reading transcripts outside the transcripts app risks serving "
            "unapproved words: go through approved_transcript_for instead "
            f"(ADR-014 §3). {offenders}"
        )

    def test_the_guard_recognises_the_pattern_it_looks_for(self) -> None:
        """ADR-006: a structural guard nobody has seen fire is not a guard.
        Parsed directly rather than planted in the tree, which would fail the
        suite for everyone until it was removed."""
        offending = ast.parse("from apps.transcripts.models import TranscriptSegment\n")

        found = [
            node
            for node in ast.walk(offending)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and "transcripts.models" in node.module
            and {alias.name for alias in node.names} & {"TranscriptSegment", "Transcript"}
        ]

        assert found, "the detector no longer recognises the import it exists to find"
