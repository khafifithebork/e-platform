"""Print the operational metrics, for a person on a server.

The endpoint in `core.views` is for a scraper. This is for the moment before a
scraper exists, and for the moment after one exists when somebody wants to know
whether the endpoint or the dashboard is lying: `--prometheus` emits the exact
bytes the endpoint serves, from the same `render`.

Reports only. There is no writing anywhere in this path and a test asserts it.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.metrics import collect, render


class Command(BaseCommand):
    help = "Print queue depth, webhook lag and transcription age. Reads only; never writes."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--prometheus",
            action="store_true",
            help="Emit the exposition format, byte-identical to what /metrics serves.",
        )

    def handle(self, *args, **options) -> None:
        metrics = collect()

        if options["prometheus"]:
            # `end=""` — render already terminates with the newline the format
            # requires, and Django would otherwise add a second one.
            self.stdout.write(render(metrics), ending="")
            return

        for metric in metrics:
            if metric.value is None:
                # Said out loud rather than skipped. In the exposition format an
                # absent metric is a gap a dashboard shows; on a terminal it
                # would just be a missing line nobody notices.
                self.stdout.write(self.style.WARNING(f"{metric.name}: unavailable"))
                continue
            self.stdout.write(f"{metric.name}: {metric.value:g}")
