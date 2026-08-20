"""Transcripts and their segments, and the constraints that hold them true.

Invariant 11: invariants live in the database. Every test here writes a row a
constraint must reject and asserts PostgreSQL refuses it, matched by
constraint **name** — asserting a bare `IntegrityError` would pass when some
other constraint did the refusing, leaving the intended one untested and
green (the M4 lesson).

Two of these carry more weight than the rest.

`APPROVED` requires `reviewed_by` and `approved_at`, because ADR-014 §4 makes
the instructor the approver and an approval nobody signed is exactly the audit
gap M3's review trail exists to close.

The position constraint is **deferrable**, and so it needs a paired test under
`SET CONSTRAINTS ALL IMMEDIATE` — ADR-009 §5: under pytest-django nothing
commits, so a DEFERRED check never fires and a test asserting only that the
happy path works would stay green if someone dropped `deferrable=`.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, role: str = Role.INSTRUCTOR):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def language(db):
    from apps.catalog.models import Language

    return Language.objects.create(code="es", name="Spanish", native_name="Espanol")


@pytest.fixture
def media_asset(db, language):
    from apps.catalog.models import Course, Lesson, Section
    from apps.media_assets.models import MediaAsset, MediaAssetStatus

    instructor = _user("teacher@example.test")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", position=1
    )
    return MediaAsset.objects.create(
        lesson=lesson,
        source_object_key="masters/abc/def.mp4",
        source_bytes=2048,
        provider="fake",
        provider_asset_id="fakeasset_abc",
        provider_playback_id="fakeplay_abc",
        status=MediaAssetStatus.READY,
    )


def _transcript(media_asset, language, **overrides):
    from apps.transcripts.models import Transcript

    fields = {
        "media_asset": media_asset,
        "language": language,
        "provider": "fake",
    }
    return Transcript.objects.create(**{**fields, **overrides})


def _segment(transcript, position: int, **overrides):
    from apps.transcripts.models import TranscriptSegment

    fields = {
        "transcript": transcript,
        "position": position,
        "start_ms": position * 1000,
        "end_ms": position * 1000 + 900,
        "text": f"Segment {position}.",
    }
    return TranscriptSegment.objects.create(**{**fields, **overrides})


class TestOneTranscriptPerLanguageAndKind:
    """A second transcript of the same kind in the same language is two
    answers to one question, and the VTT endpoint would have to pick."""

    def test_a_duplicate_is_refused(self, media_asset, language) -> None:
        _transcript(media_asset, language)

        with pytest.raises(IntegrityError, match="transcript_unique_per_language_and_kind"):
            _transcript(media_asset, language)

    def test_a_translation_may_sit_beside_the_target(self, media_asset, language) -> None:
        """§5.2's argument for rows over files: a translation is a second
        Transcript against the same asset, not a second file format."""
        from apps.transcripts.models import TranscriptKind

        _transcript(media_asset, language, kind=TranscriptKind.TARGET)

        _transcript(media_asset, language, kind=TranscriptKind.TRANSLATION)

    def test_another_language_may_sit_beside_it(self, media_asset, language) -> None:
        from apps.catalog.models import Language

        french = Language.objects.create(code="fr", name="French", native_name="Francais")
        _transcript(media_asset, language)

        _transcript(media_asset, french)


class TestApprovalMustBeSigned:
    """ADR-014 §4. The instructor approves, so the approval has to name them."""

    def test_approved_without_a_reviewer_is_refused(self, media_asset, language) -> None:
        from apps.transcripts.models import TranscriptStatus

        with pytest.raises(IntegrityError, match="approved_transcript_is_signed"):
            _transcript(
                media_asset,
                language,
                status=TranscriptStatus.APPROVED,
                approved_at=timezone.now(),
            )

    def test_approved_without_a_timestamp_is_refused(self, media_asset, language) -> None:
        from apps.transcripts.models import TranscriptStatus

        reviewer = _user("reviewer@example.test")

        with pytest.raises(IntegrityError, match="approved_transcript_is_signed"):
            _transcript(
                media_asset,
                language,
                status=TranscriptStatus.APPROVED,
                reviewed_by=reviewer,
            )

    def test_a_signed_approval_is_accepted(self, media_asset, language) -> None:
        """The positive twin. A constraint refusing every APPROVED row would
        satisfy both tests above and make approval impossible."""
        from apps.transcripts.models import TranscriptStatus

        reviewer = _user("reviewer@example.test")

        _transcript(
            media_asset,
            language,
            status=TranscriptStatus.APPROVED,
            reviewed_by=reviewer,
            approved_at=timezone.now(),
        )

    def test_an_unapproved_transcript_needs_no_signature(self, media_asset, language) -> None:
        """MACHINE output has no reviewer yet, and requiring one would make
        the machine's own result unstorable."""
        from apps.transcripts.models import TranscriptStatus

        _transcript(media_asset, language, status=TranscriptStatus.MACHINE)


class TestSegmentsOccupyRealTime:
    def test_an_end_before_its_start_is_refused(self, media_asset, language) -> None:
        transcript = _transcript(media_asset, language)

        with pytest.raises(IntegrityError, match="segment_ends_after_it_starts"):
            _segment(transcript, 1, start_ms=5000, end_ms=4000)

    def test_a_zero_length_segment_is_refused(self, media_asset, language) -> None:
        """A cue with no duration renders as a subtitle that never appears."""
        transcript = _transcript(media_asset, language)

        with pytest.raises(IntegrityError, match="segment_ends_after_it_starts"):
            _segment(transcript, 1, start_ms=5000, end_ms=5000)

    def test_a_negative_start_is_refused(self, media_asset, language) -> None:
        """Before the media begins. A VTT timestamp cannot express it and a
        player's behaviour on one is anybody's guess."""
        transcript = _transcript(media_asset, language)

        with pytest.raises(IntegrityError, match="segment_starts_within_the_media"):
            _segment(transcript, 1, start_ms=-1, end_ms=500)


class TestSegmentOrderIsUniqueAndDeferrable:
    def test_two_segments_cannot_share_a_position(self, media_asset, language) -> None:
        """Refused — but not at the INSERT.

        Written first as a plain duplicate insert, which did *not* raise: the
        constraint is DEFERRED, so the violation waits for a commit that
        pytest-django never performs, and the error surfaced at teardown as
        an unrelated-looking failure. Forcing IMMEDIATE is what makes the
        rejection observable, and saying so here is the point — the same
        deferral that makes a reorder possible makes a duplicate invisible
        until commit, and that is worth knowing before debugging it live.
        """
        from django.db import connection, transaction

        transcript = _transcript(media_asset, language)
        _segment(transcript, 1)

        with (
            pytest.raises(IntegrityError, match="segment_position_unique_per_transcript"),
            transaction.atomic(),
        ):
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            _segment(transcript, 1, start_ms=9000, end_ms=9500)

    def test_a_row_by_row_reorder_survives(self, media_asset, language) -> None:
        """Splitting a cue in review renumbers everything after it, and that
        renumbering passes through a duplicate position.

        Row by row rather than through an endpoint: `bulk_update` writes the
        whole permutation in one statement and PostgreSQL checks a deferrable
        constraint at end of *statement*, so an endpoint would survive by
        batching rather than by deferral (ADR-009 §5).
        """
        from django.db import transaction

        transcript = _transcript(media_asset, language)
        first = _segment(transcript, 1)
        second = _segment(transcript, 2)

        with transaction.atomic():
            first.position = 2
            first.save(update_fields=["position"])
            second.position = 1
            second.save(update_fields=["position"])

        first.refresh_from_db()
        second.refresh_from_db()
        assert (second.position, first.position) == (1, 2)

    def test_the_same_reorder_fails_when_the_constraint_is_immediate(
        self, media_asset, language
    ) -> None:
        """The twin that carries the information. Under pytest-django nothing
        commits, so a DEFERRED check never fires — without this, dropping
        `deferrable=` from the migration would leave the suite green while the
        review UI started erroring on every split."""
        from django.db import connection, transaction

        transcript = _transcript(media_asset, language)
        first = _segment(transcript, 1)
        _segment(transcript, 2)

        with pytest.raises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            first.position = 2
            first.save(update_fields=["position"])


class TestConfidenceIsAProportion:
    def test_above_one_is_refused(self, media_asset, language) -> None:
        """A provider reporting 95 rather than 0.95 would otherwise be stored
        and read as certainty by whatever surfaces it in review."""
        with pytest.raises(IntegrityError, match="confidence_is_a_proportion"):
            _transcript(media_asset, language, confidence="1.5")

    def test_below_zero_is_refused(self, media_asset, language) -> None:
        with pytest.raises(IntegrityError, match="confidence_is_a_proportion"):
            _transcript(media_asset, language, confidence="-0.1")

    def test_the_bounds_themselves_are_allowed(self, media_asset, language) -> None:
        from apps.transcripts.models import TranscriptKind

        _transcript(media_asset, language, confidence="0.0")
        _transcript(media_asset, language, kind=TranscriptKind.TRANSLATION, confidence="1.0")

    def test_confidence_may_be_unknown(self, media_asset, language) -> None:
        """A transcript that has not run yet has no score, and a default of
        zero would read as "the machine was certain it was wrong"."""
        transcript = _transcript(media_asset, language)

        assert transcript.confidence is None


class TestTheProviderJobIsRecordedButPrivate:
    def test_a_job_id_is_stored(self, media_asset, language) -> None:
        """The callback names it, so it is how an async result finds its
        transcript (T5)."""
        transcript = _transcript(media_asset, language, provider_job_id="fakejob_abc")

        assert transcript.provider_job_id == "fakejob_abc"

    def test_two_transcripts_cannot_share_a_job(self, media_asset, language) -> None:
        """A callback that matched two rows would apply one provider's result
        to somebody else's lesson."""
        from apps.catalog.models import Language

        french = Language.objects.create(code="fr", name="French", native_name="Francais")
        _transcript(media_asset, language, provider_job_id="fakejob_abc")

        with pytest.raises(IntegrityError, match="transcript_unique_per_provider_job"):
            _transcript(media_asset, french, provider_job_id="fakejob_abc")

    def test_many_transcripts_may_have_no_job_yet(self, media_asset, language) -> None:
        """NULLs do not collide, so every not-yet-submitted transcript can
        coexist — the same reason M4's provider_subscription_id is NULL."""
        from apps.catalog.models import Language

        french = Language.objects.create(code="fr", name="French", native_name="Francais")

        _transcript(media_asset, language)
        _transcript(media_asset, french)


class TestDeletingCascadesFromTheAsset:
    def test_segments_go_with_their_transcript(self, media_asset, language) -> None:
        """A segment without a transcript is orphaned text nothing can render
        or scope, so it is a CASCADE rather than a PROTECT."""
        from apps.transcripts.models import TranscriptSegment

        transcript = _transcript(media_asset, language)
        _segment(transcript, 1)

        transcript.delete()

        assert not TranscriptSegment.objects.exists()
