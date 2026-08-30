"""The second business alert. M14 T6.

architecture.md §3.7 lists "stuck transcriptions" among the business alerts and
calls that row *"the one people skip and shouldn't"*. M14 T4 built the
machinery and used it for entitlement drift only; this is the second thing it
was built for, and it inherits T4's two rules: say nothing when there is
nothing to say, and name what was found without naming whose it is.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail

from apps.core.metrics import STUCK_TRANSCRIPTION_AGE
from apps.transcripts.models import TranscriptStatus
from apps.transcripts.tasks import alert_on_stuck_transcriptions

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configured(settings):
    settings.OPERATIONS_ALERT_EMAIL = "ops@example.test"


class TestItStaysQuietWhenItShould:
    def test_nothing_outstanding_sends_nothing(self) -> None:
        """M14 §6 case 5. A nightly "0 stuck transcriptions" is how a real one
        gets filtered into a folder nobody opens."""
        alert_on_stuck_transcriptions.apply()

        assert mail.outbox == []

    def test_recent_work_sends_nothing(self, transcript_factory) -> None:
        """Transcription is asynchronous and review is done by people, so a
        threshold that fires over a normal weekend is one somebody mutes."""
        transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=1))

        alert_on_stuck_transcriptions.apply()

        assert mail.outbox == []

    def test_no_configured_address_sends_nothing_and_does_not_raise(
        self, settings, transcript_factory, caplog
    ) -> None:
        """Configured-off is not an error, and the finding still reaches the
        log — the half that does not depend on anyone having set an address."""
        settings.OPERATIONS_ALERT_EMAIL = ""
        transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=30))

        alert_on_stuck_transcriptions.apply()

        assert mail.outbox == []
        assert "stuck transcriptions" in caplog.text


class TestWhatItSaysWhenItFires:
    @pytest.fixture(autouse=True)
    def _backlog(self, transcript_factory):
        transcript_factory(
            status=TranscriptStatus.PENDING, age=STUCK_TRANSCRIPTION_AGE + timedelta(days=6)
        )
        transcript_factory(status=TranscriptStatus.IN_REVIEW, age=timedelta(days=4))

    def test_it_sends_one_message_to_the_operations_address(self) -> None:
        alert_on_stuck_transcriptions.apply()

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["ops@example.test"]

    def test_the_subject_carries_the_two_numbers(self) -> None:
        """Both, because they fail differently: a large count with a small age
        is a busy week, a small count with a large age is a job that died."""
        alert_on_stuck_transcriptions.apply()

        assert "2" in mail.outbox[0].subject
        assert "9 days" in mail.outbox[0].subject

    def test_it_names_no_lesson_course_or_person(self, transcript_factory) -> None:
        """M14 §6 case 6, at the surface. A transcript belongs to a lesson, a
        lesson to a course, a course to an instructor — so naming one puts a
        person's unfinished work in a mailbox nobody audits.

        Asserted against fixtures whose titles and addresses are distinctive,
        so this fails if a future template renders the objects rather than the
        two numbers the report carries."""
        alert_on_stuck_transcriptions.apply()
        message = mail.outbox[0].subject + mail.outbox[0].body

        assert "metrics-instructor@example.test" not in message
        assert "metrics-spanish" not in message
        assert "Lesson 1" not in message

    def test_it_says_what_to_run_to_see_more(self) -> None:
        """The alert deliberately carries no ids, so it has to say where the
        detail lives or it is a dead end."""
        alert_on_stuck_transcriptions.apply()

        assert "report_metrics" in mail.outbox[0].body

    def test_it_does_not_promise_a_repair(self) -> None:
        """Retrying a transcription costs money at a provider. The same line
        T4 drew for a different reason — there a second writer, here a bill."""
        alert_on_stuck_transcriptions.apply()

        assert "does not repair" in mail.outbox[0].body

    def test_the_subject_has_no_newline(self) -> None:
        """A subject is a mail header, and a newline in one is header
        injection. Django's BadHeaderError is the backstop, not the plan."""
        alert_on_stuck_transcriptions.apply()

        assert "\n" not in mail.outbox[0].subject


class TestItIsScheduled:
    def test_beat_runs_it(self, settings) -> None:
        """An alert nobody runs is an alert that does not exist. T4 made the
        same assertion for the drift job, and `test_celery.py` separately
        resolves every scheduled path against the task registry — so this
        cannot point at a task that is not there."""
        assert "stuck-transcription-alert" in settings.CELERY_BEAT_SCHEDULE

    def test_it_does_not_run_at_the_same_minute_as_the_drift_alert(self, settings) -> None:
        """Two alerts landing in the same second read as one incident, and the
        first thing anybody does with two simultaneous emails is assume they
        are about the same thing."""
        schedule = settings.CELERY_BEAT_SCHEDULE

        assert (
            schedule["stuck-transcription-alert"]["schedule"]
            != schedule["entitlement-drift-alert"]["schedule"]
        )
