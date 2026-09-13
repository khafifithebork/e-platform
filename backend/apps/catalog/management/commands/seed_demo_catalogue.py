"""Fill the catalogue with a handful of realistic-looking published courses.

`seed_catalogue` exists for load testing, and it says so in its own docstring:
titles and descriptions are words sampled at random ("Conversation Travel 7",
"Portuguese Travel Intensive Travel Conversation Everyday..."), and every
course has zero sections. That is correct for measuring an index scan over a
few thousand rows and useless for looking at a rendered page — a redesign
reviewed against word salad tells you nothing about how real course copy
sits in the layout.

This is that second, narrower need: a small, fixed set of courses with real
section and lesson titles, so `/`, `/courses`, and `/courses/{slug}` can be
judged against content instead of noise. Same discipline as
`seed_catalogue.py` — DEBUG-only, idempotent, a distinct slug prefix so it
can be told apart and cleared on its own.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import InstructorProfile, Role, User
from apps.catalog.models import Course, CourseStatus, Language, Lesson, LessonType, Level, Section
from apps.catalog.services import refresh_search_vector

PREFIX = "demo-"

# One instructor persona per course, consistent with the demo accounts a
# session's `billing`/account setup already creates — the point is a
# catalogue that reads as real, not a research exercise in variety.
COURSES = [
    {
        "slug": "spanish-conversation-a2",
        "title": "Spanish Conversation for Everyday Situations",
        "description": (
            "Order food, ask for directions, and talk about your day — the "
            "conversations that come up constantly and that most courses "
            "skip past on the way to grammar. Built around dialogues you can "
            "actually use the same week you learn them."
        ),
        "language": ("es", "Spanish", "Español"),
        "level": Level.A2,
        "skill_areas": ["speaking", "listening"],
        "sections": [
            (
                "Getting around",
                [
                    ("Asking for directions", LessonType.VIDEO, True),
                    ("Taking a taxi or the metro", LessonType.VIDEO, False),
                    ("Talking about where you're from", LessonType.AUDIO, False),
                ],
            ),
            (
                "Eating out",
                [
                    ("Ordering at a restaurant", LessonType.VIDEO, False),
                    ("Asking about ingredients and allergies", LessonType.AUDIO, False),
                    ("Paying and leaving a tip", LessonType.TEXT, False),
                ],
            ),
        ],
    },
    {
        "slug": "french-grammar-foundations",
        "title": "French Grammar Foundations",
        "description": (
            "The grammar that everything else depends on: verb conjugation, "
            "gender agreement, and the tenses you need before you can hold a "
            "real conversation. Slower and more thorough than a phrasebook, "
            "on purpose."
        ),
        "language": ("fr", "French", "Français"),
        "level": Level.A1,
        "skill_areas": ["grammar", "writing"],
        "sections": [
            (
                "The present tense",
                [
                    ("Regular -er verbs", LessonType.VIDEO, True),
                    ("Être and avoir", LessonType.VIDEO, False),
                    ("Asking questions", LessonType.TEXT, False),
                ],
            ),
            (
                "Nouns and agreement",
                [
                    ("Masculine and feminine", LessonType.VIDEO, False),
                    ("Plurals and exceptions", LessonType.AUDIO, False),
                ],
            ),
        ],
    },
    {
        "slug": "business-japanese-intro",
        "title": "Introduction to Business Japanese",
        "description": (
            "Keigo, meeting etiquette, and the set phrases that show up in "
            "every email and every meeting — for someone who already speaks "
            "conversational Japanese and needs the professional register."
        ),
        "language": ("ja", "Japanese", "日本語"),
        "level": Level.B1,
        "skill_areas": ["speaking", "writing"],
        "sections": [
            (
                "Keigo basics",
                [
                    ("Why Japanese has three levels of politeness", LessonType.VIDEO, True),
                    ("Sonkeigo and kenjougo in practice", LessonType.VIDEO, False),
                    ("Common mistakes learners make", LessonType.AUDIO, False),
                ],
            ),
            (
                "Meetings and email",
                [
                    ("Opening and closing an email", LessonType.TEXT, False),
                    ("Scheduling and rescheduling politely", LessonType.VIDEO, False),
                ],
            ),
        ],
    },
    {
        "slug": "german-for-travel",
        "title": "German for Travel",
        "description": (
            "A short, practical course for a trip rather than a degree: "
            "check-in at a hotel, read a menu, and handle the small talk "
            "that comes with getting around a German-speaking country."
        ),
        "language": ("de", "German", "Deutsch"),
        "level": Level.A1,
        "skill_areas": ["listening", "speaking"],
        "sections": [
            (
                "Arriving",
                [
                    ("At the airport and train station", LessonType.VIDEO, True),
                    ("Checking into a hotel", LessonType.AUDIO, False),
                ],
            ),
            (
                "Out and about",
                [
                    ("Reading a menu", LessonType.TEXT, False),
                    ("Small talk with strangers", LessonType.VIDEO, False),
                ],
            ),
        ],
    },
    {
        "slug": "arabic-media-advanced",
        "title": "Advanced Arabic Through the News",
        "description": (
            "Modern Standard Arabic as it actually appears in newspapers and "
            "broadcasts, for a learner who has finished the basics and wants "
            "to read and listen to real reporting without a dictionary open "
            "the whole time."
        ),
        "language": ("ar", "Arabic", "العربية"),
        "level": Level.C1,
        "skill_areas": ["reading", "listening"],
        "sections": [
            (
                "Reading the news",
                [
                    ("Headline structure and common vocabulary", LessonType.TEXT, True),
                    ("A full article, annotated", LessonType.TEXT, False),
                ],
            ),
            (
                "Listening to broadcasts",
                [
                    ("Following a news segment at natural speed", LessonType.AUDIO, False),
                    ("Regional accents in broadcast Arabic", LessonType.AUDIO, False),
                ],
            ),
        ],
    },
]


class Command(BaseCommand):
    help = "Create a small set of realistic, published demo courses. Development only."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--clear", action="store_true", help="Remove seeded demo courses.")
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG off.")

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed with DEBUG off. This writes fabricated courses; "
                "pass --force if that is genuinely what you want."
            )

        if options["clear"]:
            deleted, _ = Course.objects.filter(slug__startswith=PREFIX).delete()
            self.stdout.write(self.style.SUCCESS(f"Removed {deleted} demo object(s)."))
            return

        instructor = self._instructor()
        now = timezone.now()
        created = 0

        with transaction.atomic():
            for spec in COURSES:
                slug = f"{PREFIX}{spec['slug']}"
                if Course.objects.filter(slug=slug).exists():
                    continue

                code, name, native = spec["language"]
                language, _ = Language.objects.get_or_create(
                    code=code, defaults={"name": name, "native_name": native}
                )

                course = Course.objects.create(
                    slug=slug,
                    title=spec["title"],
                    description=spec["description"],
                    language=language,
                    level=spec["level"],
                    skill_areas=spec["skill_areas"],
                    instructor=instructor,
                    status=CourseStatus.PUBLISHED,
                    published_at=now,
                )

                for section_position, (section_title, lessons) in enumerate(spec["sections"]):
                    section = Section.objects.create(
                        course=course, title=section_title, position=section_position
                    )
                    for lesson_position, (lesson_title, lesson_type, is_preview) in enumerate(
                        lessons
                    ):
                        Lesson.objects.create(
                            course=course,
                            section=section,
                            slug=_slugify(lesson_title),
                            title=lesson_title,
                            lesson_type=lesson_type,
                            position=lesson_position,
                            is_preview=is_preview,
                        )

                refresh_search_vector(course=course)
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} demo course(s)."))

    def _instructor(self) -> User:
        # Reuses the account a dev session's `createsuperuser`/manual setup
        # already knows about, rather than inventing a throwaway persona —
        # `instructor@example.com` becomes the author of every demo course.
        user, _ = User.objects.get_or_create(
            email="instructor@example.com",
            defaults={"role": Role.INSTRUCTOR, "is_email_verified": True},
        )
        if user.role != Role.INSTRUCTOR:
            user.role = Role.INSTRUCTOR
            user.save(update_fields=["role"])

        # `PublicCourseSerializer.get_instructor_name` reads
        # `InstructorProfile.display_name`, not anything on `User` — without
        # this every demo course would show an empty instructor line, which is
        # the one thing this command exists to make look real rather than
        # merely present.
        InstructorProfile.objects.get_or_create(
            user=user, defaults={"display_name": "Amina Idrissi"}
        )
        return user


def _slugify(title: str) -> str:
    # A minimal slugify rather than importing one: lesson slugs only need to
    # be unique per course (invariant enforced by the model), not globally,
    # and every title here is plain ASCII.
    return title.lower().replace("'", "").replace(",", "").replace(" ", "-")
