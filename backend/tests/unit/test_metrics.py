"""The numbers, and the rules about what a metric may say. M14 T6.

The endpoint has its own tests. This covers the arithmetic and the three rules
`core/metrics.py` states, each of which is a failure rather than a preference:
an unreadable metric is absent rather than an error, no metric carries an
identifier, and nothing here writes.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.metrics import (
    STUCK_TRANSCRIPTION_AGE,
    Metric,
    collect,
    render,
    stuck_transcriptions,
)
from apps.core.models import WebhookEvent
from apps.transcripts.models import TranscriptStatus
from apps.transcripts.selectors import unfinished_transcriptions

pytestmark = pytest.mark.django_db


def _webhook(*, age: timedelta, processed: bool) -> WebhookEvent:
    event = WebhookEvent.objects.create(
        provider="video:fake",
        provider_event_id=f"evt-{timezone.now().timestamp()}-{age.total_seconds()}",
        event_type="asset.ready",
        processed_at=timezone.now() if processed else None,
    )
    # `created_at` is auto_now_add, so it has to be moved afterwards. An update
    # rather than a save: `save()` would trip auto_now fields and silently undo
    # the very thing being set up.
    WebhookEvent.objects.filter(pk=event.pk).update(created_at=timezone.now() - age)
    return event


class TestWebhookLag:
    def test_nothing_unprocessed_reports_zero_age(self) -> None:
        _webhook(age=timedelta(days=9), processed=True)

        numbers = {m.name: m.value for m in collect()}

        assert numbers["eplatform_webhooks_unprocessed"] == 0
        assert numbers["eplatform_webhook_oldest_unprocessed_seconds"] == 0.0

    def test_it_reports_the_oldest_not_the_newest(self) -> None:
        """The number that matters. One unprocessed event from four days ago is
        a broken handler; fifty from the last minute is a busy worker, and a
        metric reporting the newest would show the same small number in both."""
        _webhook(age=timedelta(hours=1), processed=False)
        _webhook(age=timedelta(days=4), processed=False)

        numbers = {m.name: m.value for m in collect()}

        assert numbers["eplatform_webhooks_unprocessed"] == 2
        assert numbers["eplatform_webhook_oldest_unprocessed_seconds"] == pytest.approx(
            timedelta(days=4).total_seconds(), rel=0.01
        )

    def test_a_processed_event_stops_counting(self) -> None:
        """The twin. A filter matching everything would satisfy the test above
        perfectly and report a backlog that never clears."""
        event = _webhook(age=timedelta(days=4), processed=False)
        WebhookEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())

        assert {m.name: m.value for m in collect()}["eplatform_webhooks_unprocessed"] == 0


class TestTranscriptionAge:
    def test_unfinished_work_is_counted_and_aged(self, transcript_factory) -> None:
        transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=5))

        outstanding = unfinished_transcriptions()

        assert outstanding.count == 1
        assert outstanding.oldest_age >= timedelta(days=5)

    @pytest.mark.parametrize("finished", [TranscriptStatus.APPROVED, TranscriptStatus.FAILED])
    def test_finished_work_is_excluded(self, transcript_factory, finished) -> None:
        """FAILED is excluded on purpose and is the one worth arguing about. A
        failed transcription has a status somebody can act on; counting it here
        would make the metric climb forever after one permanent failure and
        train whoever reads it to ignore the number."""
        transcript_factory(status=finished, age=timedelta(days=30))

        assert unfinished_transcriptions().count == 0

    def test_nothing_outstanding_has_no_age_rather_than_a_zero_one(
        self, transcript_factory
    ) -> None:
        """None, not `timedelta(0)`. Zero would render as a real measurement of
        an empty queue, which is indistinguishable from work that arrived this
        instant."""
        assert unfinished_transcriptions().oldest_age is None


class TestStuckTranscriptionsAreTheAlertableSubset:
    def test_recent_work_is_not_stuck(self, transcript_factory) -> None:
        """M14 §6 case 5: an alert that always fires is one nobody reads.
        Transcription is asynchronous and review is done by people, so the
        threshold must not fire on a normal weekend."""
        transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=1))

        assert stuck_transcriptions() is None

    def test_nothing_outstanding_says_nothing(self) -> None:
        assert stuck_transcriptions() is None

    def test_work_past_the_threshold_is_reported(self, transcript_factory) -> None:
        transcript_factory(
            status=TranscriptStatus.PENDING, age=STUCK_TRANSCRIPTION_AGE + timedelta(hours=1)
        )

        report = stuck_transcriptions()

        assert report is not None
        assert report.count == 1
        assert report.oldest_age_days == STUCK_TRANSCRIPTION_AGE.days

    def test_the_report_carries_no_identifiers(self, transcript_factory) -> None:
        """M14 §6 case 6. A transcript belongs to a lesson, a lesson to a
        course, a course to an instructor — so a title in an operational email
        is a person's work in a mailbox nobody audits. Asserted on the fields
        rather than on one rendered message, because a future template can only
        leak what the report carries."""
        transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=30))

        report = stuck_transcriptions()

        assert set(vars(report)) == {"count", "oldest_age_days"}


class TestTheThreeRules:
    def test_an_unreadable_metric_is_omitted_rather_than_zero(self) -> None:
        """Rule 1. A queue depth of 0 during a Redis outage is a lie a
        dashboard will believe, and a gap is a thing an alert can notice."""
        body = render([Metric("eplatform_thing", "A thing.", None)])

        assert body.strip() == ""

    def test_a_broker_that_cannot_be_reached_does_not_break_the_scrape(
        self, settings, caplog
    ) -> None:
        """Provoked with an address nothing answers rather than by patching the
        client, so this exercises the real failure — including the timeout,
        which is why the scrape returns at all."""
        settings.CELERY_BROKER_URL = "redis://127.0.0.1:6390/0"

        numbers = {m.name: m.value for m in collect()}

        assert "eplatform_celery_queue_depth" not in render(collect())
        assert numbers["eplatform_celery_queue_depth"] is None
        assert "queue depth unavailable" in caplog.text

    def test_no_metric_carries_a_label(self) -> None:
        """Rule 2, structurally. Labels are where identifiers get in — a course
        slug or a subscription id on a surface something outside this system
        scrapes and retains. No labels means no route for one."""
        for line in render(collect()).splitlines():
            if line.startswith("#"):
                continue
            name = line.split(" ")[0]
            assert "{" not in name, line

    def test_collecting_writes_nothing(self) -> None:
        """Rule 3, and the same discipline T3's reconciliation used: reads are
        counted, and a write would show up as one of them."""
        before = WebhookEvent.objects.count()

        collect()

        assert WebhookEvent.objects.count() == before

    def test_it_does_not_fan_out_per_row(
        self, transcript_factory, django_assert_num_queries
    ) -> None:
        """ADR-009: measured at two dataset sizes, asserting the count is
        *identical*. Both metrics are aggregates, so a version that loaded rows
        and summed them in Python would pass every test above."""
        transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=1))
        _webhook(age=timedelta(days=1), processed=False)
        with django_assert_num_queries(2):
            collect()

        for _ in range(4):
            transcript_factory(status=TranscriptStatus.PENDING, age=timedelta(days=1))
            _webhook(age=timedelta(days=2), processed=False)
        with django_assert_num_queries(2):
            collect()


class TestTheExpositionFormat:
    def test_each_metric_carries_help_and_type(self) -> None:
        body = render([Metric("eplatform_thing", "A thing.", 3)])

        assert body == (
            "# HELP eplatform_thing A thing.\n# TYPE eplatform_thing gauge\neplatform_thing 3\n"
        )

    def test_it_ends_with_a_newline(self) -> None:
        """Some parsers reject a body without one as truncated."""
        assert render(collect()).endswith("\n")

    def test_units_are_in_the_names(self) -> None:
        """Prometheus has no unit system, so a gauge called `webhook_lag` is a
        number somebody eventually reads as minutes."""
        for metric in collect():
            if "oldest" in metric.name:
                assert metric.name.endswith("_seconds"), metric.name


class TestTheCommand:
    def test_prometheus_output_is_what_the_endpoint_serves(self) -> None:
        """Byte-identical, from the same `render`. The point of the flag is to
        settle "is the endpoint or the dashboard lying" without a scraper."""
        out = StringIO()

        call_command("report_metrics", "--prometheus", stdout=out)

        assert out.getvalue().startswith("# HELP eplatform_")
        assert out.getvalue().endswith("\n")

    def test_the_human_form_says_when_a_metric_is_unavailable(self, settings) -> None:
        """On a terminal an omitted line is one nobody notices, which is the
        opposite of the right behaviour in the exposition format."""
        settings.CELERY_BROKER_URL = "redis://127.0.0.1:6390/0"
        out = StringIO()

        call_command("report_metrics", stdout=out)

        assert "eplatform_celery_queue_depth: unavailable" in out.getvalue()
