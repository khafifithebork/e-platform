"""Fill the catalogue with published courses, for load testing.

A baseline measured against an empty catalogue measures the framework, not the
product: an index scan over three rows and an index scan over three thousand
are the same number, and the second is the one that matters. So the load test
needs data, and the data needs to be reproducible or the baseline is a
number nobody can produce again — which ADR-022 §5 says is the difference
between a fact and an anecdote.

**Refuses to run unless `DEBUG` is on.** This writes fabricated courses under a
recognisable slug prefix, and the failure it guards against is somebody
reaching for a familiar command against a production database. `--force`
exists for a deliberate exception, and requires typing it.

Idempotent: re-running tops up to the requested count rather than duplicating.
The slug prefix is what makes that possible and also what makes cleanup a
single `--clear`.
"""

from __future__ import annotations

import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.catalog.models import Course, CourseStatus, Language
from apps.catalog.services import refresh_search_vector

PREFIX = "loadtest-"

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
SKILLS = ["listening", "speaking", "reading", "writing", "grammar", "pronunciation"]
WORDS = [
    "Spanish",
    "Portuguese",
    "Conversation",
    "Grammar",
    "Pronunciation",
    "Travel",
    "Business",
    "Beginners",
    "Intensive",
    "Everyday",
]


class Command(BaseCommand):
    help = "Create published courses for load testing. Development only."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--courses", type=int, default=500)
        parser.add_argument("--languages", type=int, default=6)
        parser.add_argument(
            "--seed",
            type=int,
            default=1,
            help="Random seed. Fixed by default so two runs produce the same catalogue.",
        )
        parser.add_argument("--clear", action="store_true", help="Remove seeded courses instead.")
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG off.")

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed with DEBUG off. This writes fabricated courses; "
                "pass --force if that is genuinely what you want."
            )

        if options["clear"]:
            deleted, _ = Course.objects.filter(slug__startswith=PREFIX).delete()
            self.stdout.write(self.style.SUCCESS(f"Removed {deleted} seeded object(s)."))
            return

        # Fixed seed by default: a baseline measured against a different
        # catalogue each run is not a baseline.
        rng = random.Random(options["seed"])  # noqa: S311 - fixtures, not crypto

        wanted = options["courses"]
        existing = Course.objects.filter(slug__startswith=PREFIX).count()
        if existing >= wanted:
            self.stdout.write(f"Already {existing} seeded courses; nothing to do.")
            return

        languages = self._languages(options["languages"])
        instructor = self._instructor()
        now = timezone.now()

        created = 0
        with transaction.atomic():
            for index in range(existing, wanted):
                title = f"{rng.choice(WORDS)} {rng.choice(WORDS)} {index}"
                course = Course.objects.create(
                    slug=f"{PREFIX}{index}",
                    title=title,
                    description=" ".join(rng.choices(WORDS, k=25)),
                    language=rng.choice(languages),
                    level=rng.choice(LEVELS),
                    skill_areas=rng.sample(SKILLS, k=2),
                    instructor=instructor,
                    status=CourseStatus.PUBLISHED,
                    published_at=now,
                )
                refresh_search_vector(course=course)
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} course(s); {wanted} total."))

    def _languages(self, count: int) -> list[Language]:
        codes = ["es", "pt", "fr", "de", "it", "ar", "ja", "zh"][:count]
        return [
            Language.objects.get_or_create(
                code=code, defaults={"name": code.upper(), "native_name": code.upper()}
            )[0]
            for code in codes
        ]

    def _instructor(self) -> User:
        user, created = User.objects.get_or_create(
            email="loadtest-instructor@example.test",
            defaults={"role": Role.INSTRUCTOR, "is_email_verified": True},
        )
        if created:
            # Unusable rather than blank: a seeded account must not be a way in.
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user
