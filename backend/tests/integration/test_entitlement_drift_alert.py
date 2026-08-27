"""The nightly entitlement drift alert. M14 T4, abuse cases 5 and 6.

T3 built a report. This is the half that means somebody finds out, and ADR-002
§4 rates the pair above paid redundancy. The failure it exists for — a lapsed
subscription still serving paid content — never announces itself, so a report
nobody runs is a report that does not exist.

**Case 5 is the one most of this file is about.** An alert that always fires is
one nobody reads, and this job runs every day for the life of the product. The
overwhelmingly common outcome is nothing, and it has to be *silent* nothing or
the rare one is invisible. `TestItStaysQuiet` is the negative half, and it is
worth more than the positive half.

**Case 6 is why the message carries subscription ids.** An alert lands in a
mailbox nobody audits, and a `Subscription` reaches a `User` in one hop, so
printing the owner is the obvious convenience and the wrong one.

The Beat wiring is asserted here too, structurally. `django-celery-beat` is a
§5-approved dependency as of this task, and ADR-001 §2.2 fixed *how* it runs:
one replica, schedule in Postgres. Both of those decay silently — a schedule
that stops being scheduled produces exactly the same empty mailbox as a system
with nothing to report.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from django.utils import timezone

from apps.accounts.models import User
from apps.entitlements.models import Subscription, SubscriptionStatus
from apps.entitlements.tasks import alert_on_entitlement_drift

pytestmark = pytest.mark.django_db

TASK_PATH = "apps.entitlements.tasks.alert_on_entitlement_drift"
PASSWORD = "a-long-enough-passphrase"
OPERATOR = "ops@example.test"


@pytest.fixture(autouse=True)
def _an_operator_to_alert(settings):
    settings.OPERATIONS_ALERT_EMAIL = OPERATOR


# The alert task chains into `deliver_email`, which is itself a task. What makes
# the outbox fill is `CELERY_TASK_ALWAYS_EAGER` in `config/settings/test.py` —
# stated here rather than re-set locally, because a fixture setting it again
# would imply the fixture is what makes these tests work. It is not: Celery
# reads that configuration once at app setup, so a per-test override would be a
# no-op that looked like a control.


def _subscription(email: str, status: str, *, period_end) -> Subscription:
    user = User.objects.create_user(email=email, password=PASSWORD)
    return Subscription.objects.create(
        user=user,
        status=status,
        current_period_end=period_end,
        provider="fake",
    )


def _lapsed(email: str = "lapsed@example.test") -> Subscription:
    """ACTIVE, three days past the period it was paid for. The resolver still
    grants it; nothing else notices."""
    return _subscription(
        email,
        SubscriptionStatus.ACTIVE,
        period_end=timezone.now() - timedelta(days=3),
    )


def _stale_cancelled() -> Subscription:
    return _subscription(
        "gone@example.test",
        SubscriptionStatus.CANCELED,
        period_end=timezone.now() - timedelta(days=9),
    )


class TestItStaysQuiet:
    """Abuse case 5, and the half that decides whether the alert is read."""

    def test_a_clean_database_sends_nothing(self) -> None:
        _subscription(
            "paying@example.test",
            SubscriptionStatus.ACTIVE,
            period_end=timezone.now() + timedelta(days=20),
        )

        alert_on_entitlement_drift()

        assert mail.outbox == []

    def test_an_empty_database_sends_nothing(self) -> None:
        """The first night after launch, and every night of a healthy system.
        A job that mails "nothing to report" daily is a filter rule within a
        week, and after that the real one is filtered too."""
        alert_on_entitlement_drift()

        assert mail.outbox == []

    def test_it_still_says_it_ran(self, caplog) -> None:
        """The twin. Silence when clean is correct, and indistinguishable from
        the job not running at all — so the log carries what the mailbox
        deliberately does not."""
        import logging

        with caplog.at_level(logging.INFO, logger="apps.entitlements.tasks"):
            alert_on_entitlement_drift()

        events = [record.event for record in caplog.records if hasattr(record, "event")]

        assert "entitlement_reconciliation_ran" in events


class TestItSpeaksUp:
    def test_drift_sends_exactly_one_email(self) -> None:
        _lapsed()
        _stale_cancelled()

        alert_on_entitlement_drift()

        assert len(mail.outbox) == 1

    def test_it_goes_to_the_configured_operator(self) -> None:
        _lapsed()

        alert_on_entitlement_drift()

        assert mail.outbox[0].to == [OPERATOR]

    def test_the_subject_says_access_is_being_granted(self) -> None:
        """The subject line is the whole message for anybody reading on a
        phone at 6am. Burying "granting access" in the body means the
        distinction T3 went to trouble to draw is not the one that reaches
        the reader."""
        _lapsed()

        alert_on_entitlement_drift()

        assert "granting access" in mail.outbox[0].subject

    def test_the_subject_does_not_claim_that_for_stale_rows(self) -> None:
        """The negative that makes the subject line mean anything. A CANCELED
        row past its period is refusing access correctly, and an alert that
        calls that "granting access" is one that gets ignored the third time."""
        _stale_cancelled()

        alert_on_entitlement_drift()

        assert "granting access" not in mail.outbox[0].subject

    def test_the_body_names_the_category_and_the_ids(self) -> None:
        subscription = _lapsed()

        alert_on_entitlement_drift()
        body = mail.outbox[0].body

        assert "ACTIVE_PAST_PERIOD" in body
        assert str(subscription.pk) in body

    def test_the_body_separates_the_dangerous_from_the_stale(self) -> None:
        """Both categories appear, and not in one undifferentiated list. A
        message that lumps a lapsed ACTIVE row in with a stale CANCELED one
        trains the reader to assume neither matters."""
        _lapsed()
        _stale_cancelled()

        body = _run_and_read_body()

        assert body.index("ACTIVE_PAST_PERIOD") < body.index("CANCELED_PAST_PERIOD")
        assert "GRANTING ACCESS" in body


class TestItLeaksNobody:
    """Abuse case 6. This message lands in a mailbox nobody audits."""

    def test_the_body_carries_no_email_address(self) -> None:
        _lapsed()

        alert_on_entitlement_drift()

        assert "lapsed@example.test" not in mail.outbox[0].body

    def test_the_subject_carries_no_email_address_either(self) -> None:
        _lapsed()

        alert_on_entitlement_drift()

        assert "lapsed@example.test" not in mail.outbox[0].subject


class TestAnUnconfiguredRecipient:
    def test_nothing_is_sent(self, settings) -> None:
        """An alert with nowhere to go must not invent somewhere. A plausible
        default address goes to a mailbox nobody watches, which is worse than
        not sending — it looks like the alerting works."""
        settings.OPERATIONS_ALERT_EMAIL = ""
        _lapsed()

        alert_on_entitlement_drift()

        assert mail.outbox == []

    def test_but_it_is_logged_as_unreported(self, settings, caplog) -> None:
        """The twin, and the reason the case above is not a silent success.
        Drift was found and deliberately not delivered; that is worth a
        warning, not a shrug."""
        import logging

        settings.OPERATIONS_ALERT_EMAIL = ""
        _lapsed()

        with caplog.at_level(logging.WARNING, logger="apps.entitlements.tasks"):
            alert_on_entitlement_drift()

        events = [record.event for record in caplog.records if hasattr(record, "event")]

        assert "entitlement_drift_unreported_no_recipient" in events

    def test_the_default_is_unconfigured(self) -> None:
        """`.env.example` documents the name and nothing fills it in. A
        default that happened to be a real address would mean the first deploy
        mails a stranger."""
        from config.settings import base

        assert base.env("OPERATIONS_ALERT_EMAIL", default="") in ("", OPERATOR)


class TestItDoesNotRepair:
    """Invariant 3 again, one layer up. T3's selector is read-only; a task that
    wrapped it in a fix would put a second writer of subscription state on a
    nightly timer, where nobody would see it happen."""

    def test_the_drifted_row_is_untouched(self) -> None:
        subscription = _lapsed()
        before = (subscription.status, subscription.current_period_end, subscription.updated_at)

        alert_on_entitlement_drift()
        subscription.refresh_from_db()

        assert (
            subscription.status,
            subscription.current_period_end,
            subscription.updated_at,
        ) == before

    def test_it_alerts_again_the_next_night(self) -> None:
        """No deduplication, and that is a decision. Drift still present on day
        three is still a live problem — a quieter one is not a fixed one, and
        suppressing repeats needs state ADR-020 §8 deliberately does not keep."""
        _lapsed()

        alert_on_entitlement_drift()
        alert_on_entitlement_drift()

        assert len(mail.outbox) == 2


class TestTheSchedule:
    """Structural, because a schedule that stops being scheduled produces
    exactly the same empty mailbox as a system with nothing to report."""

    def test_the_task_is_in_the_beat_schedule(self) -> None:
        tasks = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        assert TASK_PATH in tasks

    def test_every_scheduled_path_resolves_to_a_real_task(self) -> None:
        """The twin, and the one that catches a rename.

        A `beat_schedule` entry is a string. Renaming or moving the task leaves
        the schedule pointing at nothing, Beat logs an unregistered-task error
        nightly into a log nobody reads, and the mailbox stays empty exactly as
        it does when all is well.

        Every entry, resolved from the schedule itself — an earlier version
        asserted `TASK_PATH in app.tasks`, which is a fact about the constant
        at the top of this file and stayed true while the schedule pointed
        somewhere else entirely. Found by provoking it.
        """
        from config.celery import app

        scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        assert scheduled <= set(app.tasks), scheduled - set(app.tasks)

    def test_the_scheduler_keeps_its_state_in_the_database(self) -> None:
        """Invariant 5. Celery's default scheduler writes `celerybeat-schedule`
        to local disk, and a container that loses that file loses its record of
        when each job last ran."""
        assert settings.CELERY_BEAT_SCHEDULER == "django_celery_beat.schedulers:DatabaseScheduler"

    def test_the_scheduler_app_is_installed(self) -> None:
        """The twin. The setting names a class in a package Django has to have
        loaded for its models — and therefore its tables — to exist."""
        assert "django_celery_beat" in settings.INSTALLED_APPS


class TestTheWorkerRunsBeat:
    """ADR-001 §2.2: Beat runs inside the worker, at exactly one replica.

    Read out of the compose file rather than assumed, because the flag was
    absent for fourteen milestones with a comment promising it would arrive —
    and the comment is not what starts the scheduler.
    """

    @staticmethod
    def _worker_service() -> str:
        compose = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        start = compose.index("\n  worker:")
        return compose[start : compose.index("\n  web:", start)]

    @classmethod
    def _worker_command(cls) -> str:
        """The `command:` line alone, not the block around it.

        A correction found by provoking it: reading the whole service block
        meant the comment above the command — which says "--beat, as of M14
        T4" — satisfied the assertion, so removing the flag from the actual
        command left the test green. A test that passes on a comment is a test
        that guards a comment.
        """
        service = cls._worker_service()
        return next(line for line in service.splitlines() if line.strip().startswith("command:"))

    def test_the_worker_starts_beat(self) -> None:
        assert "--beat" in self._worker_command()

    def test_it_uses_the_database_scheduler(self) -> None:
        """Belt and braces with the setting, and not redundant: the CLI flag
        wins over `CELERY_BEAT_SCHEDULER`, so a worker started with `--beat`
        alone would use the file-backed default whatever settings say."""
        assert "django_celery_beat.schedulers:DatabaseScheduler" in self._worker_command()

    def test_the_replica_warning_survives(self) -> None:
        """Not decoration. Two beats means every scheduled job runs twice, and
        the next person to reach for `deploy.replicas` on this service needs to
        meet that sentence before they do."""
        assert "NEVER SCALE PAST ONE REPLICA" in self._worker_service()


def _run_and_read_body() -> str:
    alert_on_entitlement_drift()
    return mail.outbox[0].body
