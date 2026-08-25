"""Fill `Course.search_vector` for rows that predate it.

Invariant 14: a backfill is an idempotent, chunked management command, never
part of a migration. Migration `0005_search_vector` adds the column null and
stops; this is the half that touches every row, and it is separate precisely so
it can be run, watched, interrupted and run again without holding one
transaction open across the table.

**Idempotent** because it recomputes rather than skips: running it twice
produces the same vector, so there is no state to reason about after a partial
run. `--missing-only` exists for the large-table case where recomputing
everything is wasteful, and is not the default — the default should be the one
that is correct after a schema change to the weights.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from apps.catalog.models import Course
from apps.catalog.services import refresh_search_vector

DEFAULT_CHUNK = 500


class Command(BaseCommand):
    help = "Rebuild the search vector for every course, in chunks."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--chunk",
            type=int,
            default=DEFAULT_CHUNK,
            help=f"Rows per batch (default {DEFAULT_CHUNK}).",
        )
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only rows with no vector yet. Skips rows a weight change would need.",
        )

    def handle(self, *args, **options) -> None:
        chunk: int = options["chunk"]
        queryset: QuerySet[Course] = Course.objects.all()
        if options["missing_only"]:
            queryset = queryset.filter(search_vector__isnull=True)

        # Ordered by pk so the pages are stable: an unordered queryset paged
        # with slices can return the same row twice and miss another, which in
        # a backfill means silently skipping courses.
        ids = list(queryset.order_by("pk").values_list("pk", flat=True))

        done = 0
        for start in range(0, len(ids), chunk):
            for course in Course.objects.filter(pk__in=ids[start : start + chunk]):
                refresh_search_vector(course=course)
                done += 1
            self.stdout.write(f"{done}/{len(ids)}")

        self.stdout.write(self.style.SUCCESS(f"Refreshed {done} course(s)."))
