"""The review workflow — the only route to a learner seeing subtitles.

Abuse cases 2 and 6.

`approve` is the single most consequential call in M6: ADR-014 §3 put the
whole weight of "unreviewed subtitles are worse than none" on the VTT endpoint
serving only APPROVED transcripts, which makes this the one function that
decides whether a learner is served words at all.

So the tests cover what it refuses as carefully as what it does. There is no
MACHINE to APPROVED move, for anyone; there is no writable status; and an
approval always names someone, enforced in the database and asserted here.
"""

from __future__ import annotations

import pytest

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
        transcript=transcript, position=1, start_ms=0, end_ms=1500, text="Buenos días."
    )
    return transcript


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _act(client, transcript, action: str):
    return client.post(f"/api/v1/transcripts/{transcript.id}/{action}/")


class TestApprovalRequiresReview:
    """Abuse case 6, and the one control this workflow really provides."""

    def test_a_machine_transcript_cannot_be_approved_directly(self, client, transcript) -> None:
        """The rubber stamp §10 M6 warns about: approving raw machine output
        without opening it."""
        _sign_in(client, "teacher@example.test")

        response = _act(client, transcript, "approve")

        assert response.status_code == 409
        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.MACHINE

    def test_the_full_path_works(self, client, transcript) -> None:
        """The positive twin. A transition table refusing everything would
        satisfy every negative test in this file."""
        _sign_in(client, "teacher@example.test")

        assert _act(client, transcript, "start-review").status_code == 200
        assert _act(client, transcript, "approve").status_code == 200

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.APPROVED

    def test_approving_names_the_approver(self, client, transcript, instructor) -> None:
        """The database refuses an unsigned approval, so this asserts *who*
        rather than that a signature exists at all."""
        _sign_in(client, "teacher@example.test")
        _act(client, transcript, "start-review")

        _act(client, transcript, "approve")

        transcript.refresh_from_db()
        assert transcript.reviewed_by == instructor
        assert transcript.approved_at is not None

    def test_approving_twice_is_a_conflict(self, client, transcript) -> None:
        _sign_in(client, "teacher@example.test")
        _act(client, transcript, "start-review")
        _act(client, transcript, "approve")

        assert _act(client, transcript, "approve").status_code == 409

    def test_an_empty_transcript_cannot_be_approved(self, client, transcript) -> None:
        """An approved transcript with no cues renders an empty subtitle file,
        which a player advertises as "subtitles available" and then shows
        nothing — worse than none, because it looks provided."""
        TranscriptSegment.objects.filter(transcript=transcript).delete()
        _sign_in(client, "teacher@example.test")
        _act(client, transcript, "start-review")

        response = _act(client, transcript, "approve")

        assert response.status_code == 422
        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.IN_REVIEW


class TestOnlyTheOwnerMayReview:
    """Abuse case 2."""

    def test_another_instructor_cannot_start_a_review(self, client, transcript) -> None:
        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert _act(client, transcript, "start-review").status_code == 404

    def test_another_instructor_cannot_approve(self, client, transcript) -> None:
        """404, not 403 — and the status is asserted too, since a refusal that
        still wrote would be the bug."""
        Transcript.objects.filter(pk=transcript.pk).update(status=TranscriptStatus.IN_REVIEW)
        _user("rival@example.test")
        _sign_in(client, "rival@example.test")

        assert _act(client, transcript, "approve").status_code == 404
        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.IN_REVIEW

    def test_a_subscriber_cannot_approve(self, client, transcript) -> None:
        """Entitlement decides who may read a lesson. If it decided this, any
        subscriber could publish subtitles to every learner."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        student = _user("payer@example.test", Role.STUDENT)
        start_subscription(user=student, provider=FakeBillingProvider())
        Transcript.objects.filter(pk=transcript.pk).update(status=TranscriptStatus.IN_REVIEW)
        _sign_in(client, "payer@example.test")

        assert _act(client, transcript, "approve").status_code == 404

    def test_an_admin_may_approve(self, client, transcript) -> None:
        """ADR-014 §4 keeps admins in the loop for support."""
        _user("boss@example.test", Role.ADMIN)
        Transcript.objects.filter(pk=transcript.pk).update(status=TranscriptStatus.IN_REVIEW)
        _sign_in(client, "boss@example.test")

        assert _act(client, transcript, "approve").status_code == 200

    def test_anonymous_is_refused(self, client, transcript) -> None:
        assert _act(client, transcript, "start-review").status_code in (401, 403)


class TestReopening:
    def test_a_reviewer_may_put_it_back(self, client, transcript) -> None:
        """For someone who opened the wrong lesson."""
        _sign_in(client, "teacher@example.test")
        _act(client, transcript, "start-review")

        assert _act(client, transcript, "reopen").status_code == 200

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.MACHINE

    def test_an_approved_transcript_cannot_be_reopened_this_way(self, client, transcript) -> None:
        """Withdrawing an approval is what editing does, and it clears the
        signature. A second route would be a second place that has to
        remember to."""
        _sign_in(client, "teacher@example.test")
        _act(client, transcript, "start-review")
        _act(client, transcript, "approve")

        assert _act(client, transcript, "reopen").status_code == 409


class TestThereIsNoOtherRouteToApproved:
    def test_status_is_not_writable_through_the_review_endpoint(self, client, transcript) -> None:
        """A writable status would be a second route to APPROVED recording no
        reviewer and no time — and here it also decides whether learners are
        served subtitles at all."""
        _sign_in(client, "teacher@example.test")

        client.post(
            f"/api/v1/transcripts/{transcript.id}/start-review/",
            {"status": "APPROVED"},
            content_type="application/json",
        )

        transcript.refresh_from_db()
        assert transcript.status == TranscriptStatus.IN_REVIEW

    def test_an_unknown_action_is_a_404(self, client, transcript) -> None:
        """The actions are enumerated in the URL pattern, so an unknown one
        never reaches the view — it was a KeyError and a 500 before that."""
        _sign_in(client, "teacher@example.test")

        assert _act(client, transcript, "publish").status_code == 404

    def test_the_serializer_exposes_no_writable_field(self) -> None:
        """ADR-011: every field that decides something is read-only."""
        from apps.transcripts.serializers import TranscriptSerializer

        writable = {
            name for name, field in TranscriptSerializer().fields.items() if not field.read_only
        }

        assert writable == set()

    def test_the_transition_table_has_no_shortcut(self) -> None:
        """Asserted structurally as well as behaviourally: the behavioural
        test above proves the endpoint refuses it, this proves nobody can add
        it by editing one line and having the tests still pass."""
        from apps.transcripts.services import ALLOWED_TRANSITIONS

        assert (TranscriptStatus.MACHINE, TranscriptStatus.APPROVED) not in ALLOWED_TRANSITIONS
        assert (TranscriptStatus.PENDING, TranscriptStatus.APPROVED) not in ALLOWED_TRANSITIONS
        assert (TranscriptStatus.FAILED, TranscriptStatus.APPROVED) not in ALLOWED_TRANSITIONS
