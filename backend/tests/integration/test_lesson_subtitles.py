"""Serving subtitles: gated like the video, and only when approved.

Abuse cases 3, 3b, 4 and 8.

Subtitles are the lesson's content in written form. Anything looser here than
on the playback token would hand over in text what the token guards in video —
so the same two gates apply, in the same order.

And **only APPROVED is ever served.** That is the control ADR-014 §3 chose in
place of a publish gate, which makes this endpoint the one thing standing
between a learner and unreviewed words.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.transcripts.models import Transcript, TranscriptSegment, TranscriptStatus

PASSWORD = "a-long-enough-passphrase"
MACHINE_WORDS = "Lo que la máquina creyó oír."

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
def lesson(db, instructor):
    """A published lesson with an approved transcript."""
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve as approve_course
    from apps.catalog.services import submit_for_review

    admin = _user("approver@example.test", Role.ADMIN)
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
        status=TranscriptStatus.APPROVED,
        reviewed_by=instructor,
        approved_at=timezone.now(),
    )
    TranscriptSegment.objects.create(
        transcript=transcript, position=1, start_ms=0, end_ms=1500, text="Buenos días."
    )
    submit_for_review(course=course, by=instructor)
    approve_course(course=course, by=admin)
    return lesson


@pytest.fixture
def subscriber(db):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    user = _user("payer@example.test")
    start_subscription(user=user, provider=FakeBillingProvider())
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/transcript.vtt"


def _transcript(lesson) -> Transcript:
    return Transcript.objects.get(media_asset__lesson=lesson)


class TestSubtitlesAreGatedLikeTheVideo:
    """Abuse case 3."""

    def test_a_subscriber_is_served(self, client, lesson, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        response = client.get(_url(lesson))

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/vtt")
        assert b"Buenos d" in response.content

    def test_someone_without_a_subscription_is_refused(self, client, lesson) -> None:
        """Anything looser here would hand over in text what the playback
        token guards in video."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        response = client.get(_url(lesson))

        assert response.status_code == 403
        assert b"Buenos" not in response.content

    def test_an_anonymous_visitor_is_told_to_sign_in(self, client, lesson) -> None:
        response = client.get(_url(lesson))

        assert response.status_code == 403
        assert response.json()["reason"] == "LOGIN_REQUIRED"

    def test_losing_the_subscription_closes_the_subtitles_too(
        self, client, lesson, subscriber
    ) -> None:
        """Provoked in both directions with the same caller."""
        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        _sign_in(client, "payer@example.test")
        assert client.get(_url(lesson)).status_code == 200

        cancel(
            subscription=Subscription.objects.get(user=subscriber),
            provider=FakeBillingProvider(),
            immediately=True,
        )

        assert client.get(_url(lesson)).status_code == 403

    def test_a_preview_lessons_subtitles_are_public(self, client, lesson) -> None:
        """Abuse case 4. As public as its video — the resolver's first branch
        decides, and AllowAny is what lets that branch run."""
        from apps.catalog.models import Lesson

        Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)

        assert client.get(_url(lesson)).status_code == 200

    def test_an_unpublished_lesson_is_a_404_even_for_a_subscriber(
        self, client, lesson, subscriber
    ) -> None:
        """The resolver knows about subscriptions, not publication."""
        from apps.catalog.models import Course

        Course.objects.filter(pk=lesson.course_id).update(status="DRAFT")
        _sign_in(client, "payer@example.test")

        assert client.get(_url(lesson)).status_code == 404


class TestOnlyApprovedWordsAreServed:
    """Abuse case 3b — the control ADR-014 §3 chose over a publish gate."""

    @pytest.mark.parametrize("status", ["PENDING", "MACHINE", "IN_REVIEW", "FAILED"])
    def test_an_unapproved_transcript_is_not_served(
        self, client, lesson, subscriber, status
    ) -> None:
        """Unreviewed subtitles teach learners the wrong words with
        confidence. A 404 rather than a 204: an unapproved transcript is
        indistinguishable from none, and a learner has no business knowing
        that unreviewed words exist."""
        TranscriptSegment.objects.filter(transcript=_transcript(lesson)).update(text=MACHINE_WORDS)
        Transcript.objects.filter(media_asset__lesson=lesson).update(
            status=status, reviewed_by=None, approved_at=None
        )
        _sign_in(client, "payer@example.test")

        response = client.get(_url(lesson))

        assert response.status_code == 404
        assert MACHINE_WORDS.encode() not in response.content

    def test_a_lesson_with_no_transcript_is_a_404(self, client, lesson, subscriber) -> None:
        Transcript.objects.filter(media_asset__lesson=lesson).delete()
        _sign_in(client, "payer@example.test")

        assert client.get(_url(lesson)).status_code == 404

    def test_approving_makes_it_appear(self, client, lesson, subscriber) -> None:
        """The positive twin. A filter matching nothing would satisfy every
        test above and serve no subtitles at all, ever."""
        Transcript.objects.filter(media_asset__lesson=lesson).update(
            status=TranscriptStatus.IN_REVIEW, reviewed_by=None, approved_at=None
        )
        _sign_in(client, "payer@example.test")
        assert client.get(_url(lesson)).status_code == 404

        Transcript.objects.filter(media_asset__lesson=lesson).update(
            status=TranscriptStatus.APPROVED,
            reviewed_by=_user("r@example.test", Role.ADMIN),
            approved_at=timezone.now(),
        )

        assert client.get(_url(lesson)).status_code == 200


class TestCachingAndRevalidation:
    """Abuse case 8."""

    def test_an_etag_is_offered(self, client, lesson, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        assert client.get(_url(lesson))["ETag"]

    def test_an_unchanged_transcript_revalidates_to_304(self, client, lesson, subscriber) -> None:
        """A returning learner should not re-download a file that has not
        changed — subtitles are fetched on every lesson open."""
        _sign_in(client, "payer@example.test")
        etag = client.get(_url(lesson))["ETag"]

        response = client.get(_url(lesson), HTTP_IF_NONE_MATCH=etag)

        assert response.status_code == 304

    def test_an_edit_invalidates_the_cache(self, client, lesson, subscriber, instructor) -> None:
        """Asserted by fetching before and after rather than by inspecting a
        cache key — the key is an implementation detail, the stale words are
        the bug. Invalidation is by content: the edit moves the transcript's
        updated_at, so the key moves with it and nothing has to remember to
        purge."""
        from apps.transcripts.services import edit_segment

        _sign_in(client, "payer@example.test")
        assert b"Buenos d" in client.get(_url(lesson)).content

        segment = TranscriptSegment.objects.get(transcript=_transcript(lesson))
        edit_segment(segment=segment, by=instructor, text="Corregido por un humano.")
        # The edit un-approves (T6), so re-approve to keep it servable.
        Transcript.objects.filter(media_asset__lesson=lesson).update(
            status=TranscriptStatus.APPROVED,
            reviewed_by=instructor,
            approved_at=timezone.now(),
        )

        body = client.get(_url(lesson)).content
        assert b"Corregido por un humano." in body
        assert b"Buenos d" not in body

    def test_the_old_etag_stops_matching_after_an_edit(
        self, client, lesson, subscriber, instructor
    ) -> None:
        """The other half: a client holding the previous validator must be
        told the file changed rather than handed a 304."""
        from apps.transcripts.services import edit_segment

        _sign_in(client, "payer@example.test")
        stale_etag = client.get(_url(lesson))["ETag"]

        segment = TranscriptSegment.objects.get(transcript=_transcript(lesson))
        edit_segment(segment=segment, by=instructor, text="Corregido.")
        Transcript.objects.filter(media_asset__lesson=lesson).update(
            status=TranscriptStatus.APPROVED,
            reviewed_by=instructor,
            approved_at=timezone.now(),
        )

        response = client.get(_url(lesson), HTTP_IF_NONE_MATCH=stale_etag)

        assert response.status_code == 200

    def test_the_response_is_not_publicly_cacheable(self, client, lesson, subscriber) -> None:
        """Subtitles are gated content. A shared cache holding them would
        serve one learner's entitlement to the next request."""
        _sign_in(client, "payer@example.test")

        assert "private" in client.get(_url(lesson))["Cache-Control"]


class TestNothingElseLeaks:
    def test_the_provider_job_is_not_exposed(self, client, lesson, subscriber) -> None:
        """Abuse case 11."""
        _sign_in(client, "payer@example.test")

        assert b"fakejob_abc" not in client.get(_url(lesson)).content

    def test_no_playback_handle_appears(self, client, lesson, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        assert b"fakeplay_abc" not in client.get(_url(lesson)).content


class TestQueryCost:
    def test_serving_subtitles_does_not_fan_out_over_cues(
        self, client, lesson, subscriber, django_assert_num_queries
    ) -> None:
        """ADR-009. An hour of speech is several hundred cues, and this is
        fetched every time a learner opens a lesson."""
        transcript = _transcript(lesson)
        for position in range(2, 60):
            TranscriptSegment.objects.create(
                transcript=transcript,
                position=position,
                start_ms=position * 2000,
                end_ms=position * 2000 + 1500,
                text=f"Frase {position}.",
            )
        _sign_in(client, "payer@example.test")

        # Session, user, the lesson, the resolver's override and subscription
        # checks, the transcript, and its cues.
        with django_assert_num_queries(7):
            client.get(_url(lesson))
