"""The transcript panel, and the risk that comes with it.

ADR-014 §3 put the whole weight of "unreviewed subtitles are worse than none"
at the point of *serving* rather than at publication, and said plainly what
that costs: **anything else that renders segments must apply the same filter.**
M6 had one renderer, so the rule was easy to keep. This milestone adds a
second, which is when a rule like that usually stops holding.

So the test that matters here is not "the panel refuses an unapproved
transcript" — it is `TestNothingLeaksUnapprovedWords`, which walks the URL
configuration for every lesson-scoped route and asserts the words appear in
none of them. A leak is a property of the system, not of the endpoint somebody
remembered to check.
"""

from __future__ import annotations

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.models import Role
from apps.transcripts.models import Transcript, TranscriptKind, TranscriptSegment, TranscriptStatus

PASSWORD = "a-long-enough-passphrase"

# Distinctive enough that finding it in a response body cannot be a coincidence.
UNAPPROVED_WORD = "zzqx-unreviewed-utterance"

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
    from apps.media_assets.models import MediaAsset, MediaAssetStatus

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
        duration_seconds=600,
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return lesson


@pytest.fixture
def learner(db):
    return _subscribe(_user("learner@example.test"))


def _transcript(lesson, *, status: str, text: str = UNAPPROVED_WORD) -> Transcript:
    from django.utils import timezone

    transcript = Transcript.objects.create(
        media_asset=lesson.media_asset,
        language=lesson.course.language,
        kind=TranscriptKind.TARGET,
        status=status,
        provider="fake",
        provider_job_id=f"job-{status}",
        reviewed_by=_user(f"reviewer-{status}@example.test", Role.ADMIN)
        if status == TranscriptStatus.APPROVED
        else None,
        approved_at=timezone.now() if status == TranscriptStatus.APPROVED else None,
    )
    TranscriptSegment.objects.create(
        transcript=transcript, position=1, start_ms=0, end_ms=2000, text=text
    )
    TranscriptSegment.objects.create(
        transcript=transcript, position=2, start_ms=2000, end_ms=4000, text="segunda linea"
    )
    return transcript


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _panel(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/transcript/"


class TestThePanel:
    def test_an_approved_transcript_is_served_as_rows(self, client, lesson, learner) -> None:
        _transcript(lesson, status=TranscriptStatus.APPROVED, text="hola que tal")
        _sign_in(client, "learner@example.test")

        body = client.get(_panel(lesson)).json()

        assert body["language_code"] == "es"
        assert [segment["text"] for segment in body["segments"]] == [
            "hola que tal",
            "segunda linea",
        ]

    def test_cues_carry_their_timings(self, client, lesson, learner) -> None:
        """Without these the panel cannot highlight the current line or seek
        when one is clicked, which is the only reason it exists rather than
        reusing the VTT."""
        _transcript(lesson, status=TranscriptStatus.APPROVED, text="hola")
        _sign_in(client, "learner@example.test")

        first = client.get(_panel(lesson)).json()["segments"][0]

        assert (first["start_ms"], first["end_ms"]) == (0, 2000)

    def test_segments_arrive_in_order(self, client, lesson, learner) -> None:
        transcript = _transcript(lesson, status=TranscriptStatus.APPROVED, text="primera")
        TranscriptSegment.objects.create(
            transcript=transcript, position=3, start_ms=4000, end_ms=6000, text="tercera"
        )
        _sign_in(client, "learner@example.test")

        positions = [s["position"] for s in client.get(_panel(lesson)).json()["segments"]]

        assert positions == sorted(positions)

    def test_a_lesson_without_a_transcript_is_a_404(self, client, lesson, learner) -> None:
        _sign_in(client, "learner@example.test")

        assert client.get(_panel(lesson)).status_code == 404


class TestOnlyApprovedWordsAreServed:
    @pytest.mark.parametrize(
        "status", [TranscriptStatus.MACHINE, TranscriptStatus.IN_REVIEW, TranscriptStatus.FAILED]
    )
    def test_an_unapproved_transcript_is_a_404(self, client, lesson, learner, status) -> None:
        """404, not 403 and not an empty 200: an unapproved transcript must be
        indistinguishable from none at all. A learner has no business knowing
        that unreviewed words exist."""
        _transcript(lesson, status=status)
        _sign_in(client, "learner@example.test")

        response = client.get(_panel(lesson))

        assert response.status_code == 404
        assert UNAPPROVED_WORD.encode() not in response.content

    def test_but_approving_it_serves_it(self, client, lesson, learner) -> None:
        """The positive twin. A panel that 404'd unconditionally would satisfy
        every test above."""
        _transcript(lesson, status=TranscriptStatus.APPROVED)
        _sign_in(client, "learner@example.test")

        response = client.get(_panel(lesson))

        assert response.status_code == 200
        assert UNAPPROVED_WORD.encode() in response.content


class TestTheSameTwoGatesAsPlayback:
    def test_no_subscription_is_refused_with_a_reason(self, client, lesson) -> None:
        _transcript(lesson, status=TranscriptStatus.APPROVED)
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        response = client.get(_panel(lesson))

        assert response.status_code == 403
        assert response.json()["reason"] == "NO_SUBSCRIPTION"
        assert UNAPPROVED_WORD.encode() not in response.content

    def test_an_unpublished_lesson_is_a_404(self, client, lesson, learner) -> None:
        from apps.catalog.models import Course

        _transcript(lesson, status=TranscriptStatus.APPROVED)
        Course.objects.filter(pk=lesson.course_id).update(status="DRAFT")
        _sign_in(client, "learner@example.test")

        assert client.get(_panel(lesson)).status_code == 404

    def test_a_preview_lesson_needs_no_account(self, client, lesson) -> None:
        """`AllowAny`, matching the VTT view: a preview lesson's words are as
        public as its video, and the resolver's first branch is what decides
        that. A blanket authentication check would refuse them before it ran.
        """
        from apps.catalog.models import Lesson

        _transcript(lesson, status=TranscriptStatus.APPROVED)
        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)

        response = client.get(_panel(lesson))

        assert response.status_code == 200
        assert UNAPPROVED_WORD.encode() in response.content


class TestWhatTheLearnerSerializerDoesNotSay:
    def test_no_reviewer_bookkeeping_reaches_a_learner(self, client, lesson, learner) -> None:
        """Asserted against the raw bytes rather than the parsed keys, because
        a nested serializer can leak a field the top-level shape does not name.
        """
        _transcript(lesson, status=TranscriptStatus.APPROVED)
        _sign_in(client, "learner@example.test")

        content = client.get(_panel(lesson)).content

        for reviewer_only in (
            b"confidence",
            b"error_message",
            b"provider",
            b"is_edited",
            b"status",
        ):
            assert reviewer_only not in content, reviewer_only

    def test_the_check_can_see_a_field_that_is_there(self, client, lesson, learner) -> None:
        """ADR-006, applied to a negative assertion: a misspelled needle would
        make the test above pass on any response at all."""
        _transcript(lesson, status=TranscriptStatus.APPROVED)
        _sign_in(client, "learner@example.test")

        content = client.get(_panel(lesson)).content

        assert b"language_code" in content
        assert b"start_ms" in content


class TestNothingLeaksUnapprovedWords:
    """ADR-014 §3's risk, swept rather than spot-checked.

    Every lesson-scoped route in the URL configuration, found by walking it
    rather than by listing them here — a hand-kept list is exactly what stops
    being complete the day somebody adds a route.
    """

    @staticmethod
    def _lesson_routes(lesson) -> list[str]:
        found: list[str] = []

        def walk(patterns, prefix: str) -> None:
            for entry in patterns:
                route = getattr(entry.pattern, "_route", None)
                if isinstance(entry, URLResolver):
                    walk(entry.url_patterns, prefix + (route or ""))
                elif isinstance(entry, URLPattern) and route:
                    full = prefix + route
                    if "lessons/<uuid:pk>" in full:
                        found.append("/" + full.replace("<uuid:pk>", str(lesson.id)))

        walk(get_resolver().url_patterns, "")
        return found

    def test_the_sweep_finds_the_routes_it_claims_to(self, lesson) -> None:
        """The sweep is worthless if the walk returns nothing, and a walk that
        returns nothing passes every assertion below."""
        routes = self._lesson_routes(lesson)

        assert len(routes) >= 4
        assert any(route.endswith("/transcript/") for route in routes)
        assert any(route.endswith("transcript.vtt") for route in routes)

    def test_no_learner_route_leaks_unapproved_words(self, client, lesson, learner) -> None:
        _transcript(lesson, status=TranscriptStatus.MACHINE)
        _sign_in(client, "learner@example.test")

        leaked = [
            route
            for route in self._lesson_routes(lesson)
            if UNAPPROVED_WORD.encode() in client.get(route).content
        ]

        assert leaked == [], f"unreviewed words reachable at {leaked}"

    def test_nor_does_any_route_a_stranger_can_reach(self, client, lesson) -> None:
        """Anonymous, and over the public catalogue as well: the words must not
        be somewhere that never had a gate in the first place."""
        _transcript(lesson, status=TranscriptStatus.MACHINE)

        routes = [
            *self._lesson_routes(lesson),
            "/api/v1/catalogue/courses/",
            f"/api/v1/catalogue/courses/{lesson.course.slug}/",
        ]
        leaked = [
            route for route in routes if UNAPPROVED_WORD.encode() in client.get(route).content
        ]

        assert leaked == []

    def test_and_the_sweep_would_notice_if_they_did(self, client, lesson, learner) -> None:
        """The positive twin for the sweep itself. Approved, the same words
        must be found — otherwise the two tests above prove only that the walk
        cannot see anything.
        """
        _transcript(lesson, status=TranscriptStatus.APPROVED)
        _sign_in(client, "learner@example.test")

        serving = [
            route
            for route in self._lesson_routes(lesson)
            if UNAPPROVED_WORD.encode() in client.get(route).content
        ]

        assert sorted(serving) == sorted(
            [
                f"/api/v1/lessons/{lesson.id}/transcript/",
                f"/api/v1/lessons/{lesson.id}/transcript.vtt",
            ]
        )


class TestCachingAndCost:
    def test_a_returning_learner_revalidates(self, client, lesson, learner) -> None:
        _transcript(lesson, status=TranscriptStatus.APPROVED)
        _sign_in(client, "learner@example.test")
        first = client.get(_panel(lesson))

        again = client.get(_panel(lesson), HTTP_IF_NONE_MATCH=first["ETag"])

        assert again.status_code == 304

    def test_an_edit_changes_the_etag(self, client, lesson, learner) -> None:
        """The twin. An ETag that never moved would serve yesterday's wrong
        words forever."""
        from django.utils import timezone

        transcript = _transcript(lesson, status=TranscriptStatus.APPROVED)
        _sign_in(client, "learner@example.test")
        first = client.get(_panel(lesson))["ETag"]

        Transcript.objects.filter(pk=transcript.pk).update(updated_at=timezone.now())

        assert client.get(_panel(lesson))["ETag"] != first

    def test_the_panel_does_not_cost_a_query_per_cue(
        self, client, lesson, learner, django_assert_num_queries
    ) -> None:
        """ADR-009, and a corrected claim.

        This first said the prefetch is what stops six hundred cues costing
        six hundred queries. It is not: `transcript.segments.all()` is a
        reverse foreign key collection, which Django answers in one query
        however many rows come back. Removing the prefetch leaves this test
        passing — provoked, to be sure.

        What the prefetch actually buys is the ordering, and one query rather
        than two on a path that would otherwise fetch the collection twice.
        The count is still worth pinning, because *serializing* per cue is a
        real way to fan out and this is the test that would notice.

        Seven: session, user, the lesson, the resolver's two checks, the
        transcript with its language joined, and the segments. The language
        join was added after measuring — serializing `language_code` was
        dereferencing the foreign key for one small row, an eighth query for
        something a JOIN answers for free.
        """
        transcript = _transcript(lesson, status=TranscriptStatus.APPROVED)
        TranscriptSegment.objects.bulk_create(
            TranscriptSegment(
                transcript=transcript,
                position=position,
                start_ms=position * 1000,
                end_ms=position * 1000 + 900,
                text=f"linea {position}",
            )
            for position in range(3, 40)
        )
        _sign_in(client, "learner@example.test")
        client.get(_panel(lesson))

        with django_assert_num_queries(7):
            body = client.get(_panel(lesson)).json()

        # Worthless without this: an empty transcript costs fewer queries.
        assert len(body["segments"]) == 39
