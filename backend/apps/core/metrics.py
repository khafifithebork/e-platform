"""Operational numbers, and the rules about what a metric may say.

architecture.md §3.7 asks for queue depth, transcription job age and webhook
lag. This computes them. `views.metrics` renders them; the alert task reads one
of them. Keeping the arithmetic here means the endpoint and the alert cannot
disagree about what "stuck" means.

**Three rules, each of which is a failure this file exists to avoid.**

1. **A metric that cannot be read is absent, never an error.** Queue depth
   needs Redis, and a monitoring endpoint that returns 500 because the thing it
   monitors is down is worthless exactly when it is needed. An absent metric is
   visible in Prometheus as a gap; a 500 is visible as "monitoring is broken".

2. **No labels, and therefore no identifiers.** A course slug or a subscription
   id in a metric label is personal or commercial data on a surface that is
   scraped, cached and retained by something outside this system. Every metric
   here is a bare number, which is also all a dashboard needs.

3. **Read-only.** Asserted, not claimed.

**Units are in the names**, because Prometheus has no unit system and a gauge
called `webhook_lag` is a number somebody will eventually read as minutes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Min
from django.utils import timezone

from apps.core.models import WebhookEvent
from apps.transcripts.selectors import unfinished_transcriptions

logger = logging.getLogger(__name__)

PREFIX = "eplatform"

# Celery's default queue, and the only one configured — settings define no
# task routes. Named rather than discovered: asking the broker which queues
# exist returns whatever happens to have been created, so a typo in a future
# route would silently produce a metric for a queue nothing consumes.
CELERY_QUEUES = ("celery",)


@dataclass(frozen=True)
class Metric:
    name: str
    help_text: str
    value: float | None


def _webhook_metrics(now) -> list[Metric]:
    """The backlog of webhooks that arrived and were never finished.

    `WebhookEvent.processed_at` is null until the task handling it succeeds,
    and the model's own index calls these rows "the queue of things that went
    wrong". Age matters more than count: one unprocessed event from four days
    ago is a broken handler, and fifty from the last minute is a busy worker.
    """
    aggregate = WebhookEvent.objects.filter(processed_at__isnull=True).aggregate(
        count=Count("pk"), oldest=Min("created_at")
    )
    oldest = aggregate["oldest"]

    return [
        Metric(
            f"{PREFIX}_webhooks_unprocessed",
            "Webhook events received but not yet processed.",
            aggregate["count"],
        ),
        Metric(
            f"{PREFIX}_webhook_oldest_unprocessed_seconds",
            "Age of the oldest unprocessed webhook event.",
            0.0 if oldest is None else (now - oldest).total_seconds(),
        ),
    ]


def _transcription_metrics(now) -> list[Metric]:
    outstanding = unfinished_transcriptions(now=now)

    return [
        Metric(
            f"{PREFIX}_transcriptions_unfinished",
            "Transcripts that have reached neither APPROVED nor FAILED.",
            outstanding.count,
        ),
        Metric(
            f"{PREFIX}_transcription_oldest_unfinished_seconds",
            "Age of the oldest transcript still awaiting completion.",
            0.0 if outstanding.oldest_age is None else outstanding.oldest_age.total_seconds(),
        ),
    ]


def _queue_depth() -> float | None:
    """Tasks waiting in the broker, or None if the broker cannot be asked.

    A direct Redis client rather than an adapter. Invariant 4 is about
    *providers* — vendors behind a swappable seam — and Redis here is
    infrastructure in the same sense Postgres is: Celery already speaks to it
    through `CELERY_BROKER_URL` and there is nothing to swap.

    Short timeouts on purpose. This runs inside a request, and a metrics
    endpoint that hangs for the default socket timeout while Redis is
    unreachable turns one broken dependency into a scrape that never returns.

    **The broad except is the point, not laziness.** Rule 1 above: every way
    this can fail — an unreachable host, a malformed URL, an auth error — must
    produce an absent metric rather than a failed scrape. It is logged, so the
    absence has an explanation somewhere.
    """
    try:
        import redis

        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        return float(sum(client.llen(queue) for queue in CELERY_QUEUES))
    except Exception:
        logger.warning("queue depth unavailable", exc_info=True)
        return None


def collect(*, now=None) -> list[Metric]:
    """Every metric, in a stable order.

    Stable because a diff between two scrapes should be about the numbers.
    """
    now = now or timezone.now()

    return [
        Metric(
            f"{PREFIX}_celery_queue_depth",
            "Tasks waiting in the Celery broker.",
            _queue_depth(),
        ),
        *_webhook_metrics(now),
        *_transcription_metrics(now),
    ]


def render(metrics: list[Metric]) -> str:
    """Prometheus text exposition format.

    Hand-rolled rather than pulling in a client library, and that is a
    deliberate trade recorded in ADR-028 §2: the format is three lines per
    metric, we export gauges and nothing else, and a dependency would arrive
    with a registry, a process-collector and a multiprocess mode this
    application has no use for.

    Metrics whose value is None are **omitted entirely** rather than exported
    as 0 or NaN. A queue depth of 0 during a Redis outage is a lie a dashboard
    will believe.
    """
    lines: list[str] = []
    for metric in metrics:
        if metric.value is None:
            continue
        lines.append(f"# HELP {metric.name} {metric.help_text}")
        lines.append(f"# TYPE {metric.name} gauge")
        lines.append(f"{metric.name} {metric.value}")

    # The format requires a trailing newline; a scrape of a body without one is
    # rejected by some parsers as truncated.
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class UnfinishedTranscriptionsReport:
    """What the alert says. Counts and an age — no lesson titles, no ids.

    M14 §6 case 6: the alert names what it found without leaking who it belongs
    to. A transcript is attached to a lesson, a lesson to a course, and a course
    to an instructor, so a title in an operational email is a person's work in a
    mailbox nobody audits.
    """

    count: int
    oldest_age_days: int


# How long a transcript may sit unfinished before it is worth an email.
#
# Three days rather than an hour: transcription is asynchronous, review is done
# by people, and a threshold that fires on a normal weekend is a threshold
# somebody adds a mail rule for. M14 §6 case 5 — an alert that always fires is
# one nobody reads.
STUCK_TRANSCRIPTION_AGE = timedelta(days=3)


def stuck_transcriptions(*, now=None) -> UnfinishedTranscriptionsReport | None:
    """The alertable subset: outstanding work older than the threshold.

    Returns None when there is nothing to say, so the caller sends nothing
    rather than mailing a zero.
    """
    outstanding = unfinished_transcriptions(now=now)

    if outstanding.oldest_age is None or outstanding.oldest_age < STUCK_TRANSCRIPTION_AGE:
        return None

    return UnfinishedTranscriptionsReport(
        count=outstanding.count,
        oldest_age_days=outstanding.oldest_age.days,
    )
