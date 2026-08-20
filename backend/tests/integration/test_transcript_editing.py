"""Correcting what the machine heard.

Abuse cases 1 and 5, plus the half of case 7 that belongs to editing.

The test that matters most is that **an edit un-approves**. An approval
describes the words that were approved; changing them afterwards leaves an
approval standing over content nobody signed off, which is unreviewed
subtitles wearing an approval — the precise thing ADR-014 §3 arranges to keep
from learners, arriving from inside.

And clearing the *signature* matters as much as the status: a row that kept
`reviewed_by` would go on naming someone as having approved words they never
saw. The database cannot catch that — its constraint only requires a signature
*when* APPROVED — so it is asserted here.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.media_assets.models import MediaAsset, MediaAssetStatus
from apps.transcripts.models import Transcript, TranscriptSegment, TranscriptStatus

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


def _user(email: str, role: str = Role.INSTRUCTOR):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test")


@pytest.fixture
def transcript(db, instructor):
    """A machine transcript with cues, waiting for a human."""
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
        confidence="0.9",
    )
    for position, text in enumerate(["Buenos días.", "¿Cómo estás?"], start=1):
        TranscriptSegment.objects.create(
            transcript=transcript,
            position=position,
            start_ms=(position - 1) * 2000,
            end_ms=(position - 1) * 2000 + 1500,
            text=text,
        )
    return transcript


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _segment(transcript, position: int = 1) -> TranscriptSegment:
    return TranscriptSegment.objects.get(transcript=transcript, position=position)


def _edit(client, segment, **body):
    return client.patch(
        f"/api/v1/transcript-segments/{segment.id}/", body, content_type="application/json"
    )


def _approve(transcript, reviewer) -> None:
    Transcript.objects.filter(pk=transcript.pk).update(
        status=TranscriptStatus.APPROVED,
        reviewed_by=reviewer,
        approved_at=timezone.now(),
    )


class TestOnlyTheOwnerMayCorrect:
    """Abuse case 1."""

    def test_the_instructor_may_edit(self, client, transcript) -> None:
        _sign_in(client, "teacher@example.test")

        response = _edit(client, _segment(transcript), text="Buenos días a todos.")

        assert response.status_code == 200
        assert _segment(transcript).text == "Buenos días a todos."

    def test_another_instructor_gets_a_404(self, client, transcript) -> None:
        """Not 403 (§6.3), and asserted on the words as well as the status —
        a refusal that still wrote would be the bug."""
        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert _edit(client, _segment(transcript), text="Hijacked.").status_code == 404
        assert _segment(transcript).text == "Buenos días."

    def test_a_subscriber_cannot_rewrite_the_lesson(self, client, transcript) -> None:
        """Entitlement decides who may *read* a lesson. If it decided this,
        every subscriber could rewrite the teacher's words."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        student = _user("payer@example.test", Role.STUDENT)
        start_subscription(user=student, provider=FakeBillingProvider())
        _sign_in(client, "payer@example.test")

        assert _edit(client, _segment(transcript), text="Hijacked.").status_code == 404

    def test_an_admin_may_edit(self, client, transcript) -> None:
        _user("boss@example.test", Role.ADMIN)
        _sign_in(client, "boss@example.test")

        assert _edit(client, _segment(transcript), text="Corrected.").status_code == 200

    def test_anonymous_is_refused(self, client, transcript) -> None:
        assert _edit(client, _segment(transcript), text="Hijacked.").status_code in (401, 403)

    def test_reading_another_instructors_transcript_is_a_404(self, client, transcript) -> None:
        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert client.get(f"/api/v1/transcripts/{transcript.id}/").status_code == 404


class TestEditsAreMarked:
    """Abuse case 5."""

    def test_an_edited_cue_is_flagged(self, client, transcript) -> None:
        """Two things read this: a reviewer seeing which lines were touched,
        and a re-run knowing there is human work to preserve."""
        _sign_in(client, "teacher@example.test")

        _edit(client, _segment(transcript), text="Buenos días a todos.")

        assert _segment(transcript).is_edited is True

    def test_untouched_cues_stay_unflagged(self, client, transcript) -> None:
        """The positive twin: a flag set on everything would carry no
        information at all."""
        _sign_in(client, "teacher@example.test")

        _edit(client, _segment(transcript, 1), text="Corrected.")

        assert _segment(transcript, 2).is_edited is False

    def test_timings_are_editable_too(self, client, transcript) -> None:
        """A cue that starts half a word late is as wrong as a misheard verb,
        and fixing it is the same job."""
        _sign_in(client, "teacher@example.test")

        response = _edit(client, _segment(transcript), start_ms=250, end_ms=1800)

        assert response.status_code == 200
        segment = _segment(transcript)
        assert (segment.start_ms, segment.end_ms) == (250, 1800)

    def test_an_impossible_span_is_refused_with_a_400(self, client, transcript) -> None:
        """Written first as `pytest.raises(Exception)`, which passed — on a
        500, because the constraint refused the save and the IntegrityError
        reached the client. That is a server error for what is plainly a
        client mistake, and it tells a reviewer who dragged a handle too far
        that the server broke. The span is now checked at the boundary."""
        _sign_in(client, "teacher@example.test")

        response = _edit(client, _segment(transcript), start_ms=5000, end_ms=4000)

        assert response.status_code == 400
        assert _segment(transcript).start_ms == 0

    def test_a_partial_edit_cannot_invert_the_span(self, client, transcript) -> None:
        """Validated on the merged values: a request sending only `start_ms`
        can still push it past an end it never mentioned."""
        _sign_in(client, "teacher@example.test")

        response = _edit(client, _segment(transcript), start_ms=9000)

        assert response.status_code == 400

    def test_an_empty_edit_is_refused(self, client, transcript) -> None:
        _sign_in(client, "teacher@example.test")

        assert _edit(client, _segment(transcript)).status_code == 400


class TestAnEditUnApproves:
    """The half of abuse case 7 that belongs to editing."""

    def test_editing_an_approved_transcript_returns_it_to_review(self, client, transcript) -> None:
        """An approval describes the words that were approved. Changing them
        afterwards leaves an approval standing over content nobody signed —
        unreviewed subtitles wearing an approval."""
        reviewer = _user("reviewer@example.test", Role.ADMIN)
        _approve(transcript, reviewer)
        _sign_in(client, "teacher@example.test")

        _edit(client, _segment(transcript), text="Actually, something else.")

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.IN_REVIEW

    def test_the_signature_is_cleared_too(self, client, transcript) -> None:
        """Matters as much as the status. A row keeping reviewed_by would go
        on naming someone as having approved words they never saw — and the
        database cannot catch it, because the constraint only requires a
        signature *when* APPROVED."""
        reviewer = _user("reviewer@example.test", Role.ADMIN)
        _approve(transcript, reviewer)
        _sign_in(client, "teacher@example.test")

        _edit(client, _segment(transcript), text="Actually, something else.")

        transcript.refresh_from_db()
        assert transcript.reviewed_by is None
        assert transcript.approved_at is None

    def test_editing_a_machine_transcript_does_not_change_its_status(
        self, client, transcript
    ) -> None:
        """MACHINE and IN_REVIEW both mean "not approved". Promoting on edit
        would guess that a correction is the start of a review; T7 makes that
        an explicit act instead."""
        _sign_in(client, "teacher@example.test")

        _edit(client, _segment(transcript), text="Corrected.")

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.MACHINE


class TestWhenEditingIsRefused:
    def test_a_pending_transcript_has_nothing_to_edit(self, client, transcript) -> None:
        """The machine has not answered yet."""
        Transcript.objects.filter(pk=transcript.pk).update(status=TranscriptStatus.PENDING)
        _sign_in(client, "teacher@example.test")

        assert _edit(client, _segment(transcript), text="x").status_code == 409

    def test_a_failed_transcript_is_fixed_by_retrying_not_typing(self, client, transcript) -> None:
        Transcript.objects.filter(pk=transcript.pk).update(status=TranscriptStatus.FAILED)
        _sign_in(client, "teacher@example.test")

        assert _edit(client, _segment(transcript), text="x").status_code == 409


class TestTheReviewScreen:
    def test_it_returns_every_cue_in_order(self, client, transcript) -> None:
        """Unpaginated on purpose: the task is reading a lesson end to end,
        and paginating it makes that a loop."""
        _sign_in(client, "teacher@example.test")

        body = client.get(f"/api/v1/transcripts/{transcript.id}/").json()

        assert [segment["position"] for segment in body["segments"]] == [1, 2]

    def test_it_does_not_expose_the_provider_job(self, client, transcript) -> None:
        """Abuse case 11. A support handle, of no use on a review screen."""
        _sign_in(client, "teacher@example.test")

        response = client.get(f"/api/v1/transcripts/{transcript.id}/")

        assert b"fakejob_abc" not in response.content

    def test_it_does_not_fan_out_over_the_cues(
        self, client, transcript, django_assert_num_queries
    ) -> None:
        """ADR-009. An hour of speech is several hundred cues, so one query
        per cue is the difference between a review screen and a timeout."""
        for position in range(3, 40):
            TranscriptSegment.objects.create(
                transcript=transcript,
                position=position,
                start_ms=position * 2000,
                end_ms=position * 2000 + 1500,
                text=f"Frase {position}.",
            )
        _sign_in(client, "teacher@example.test")

        # Session, user, the transcript with its joins, and the cues.
        with django_assert_num_queries(4):
            client.get(f"/api/v1/transcripts/{transcript.id}/")
