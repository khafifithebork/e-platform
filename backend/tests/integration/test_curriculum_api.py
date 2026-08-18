"""Sections, lessons, and reordering.

Abuse case 7 is the interesting one: a reorder takes a list of ids, so it is
the easiest place in the whole API to smuggle in a row belonging to somebody
else. The test sends one and asserts that *nothing* moved — a partial reorder
that rejects the foreign id but applies the rest is still a bug, because the
caller's course silently ends up in an order they did not ask for.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _instructor(email: str):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


def _course(slug: str, owner_email: str):
    from apps.catalog.models import Course, Language

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Español"}
    )
    return Course.objects.create(
        slug=slug,
        title=slug,
        language=language,
        level="A1",
        instructor=_instructor(owner_email),
    )


@pytest.fixture
def mine(db):
    return _course("mine", "me@example.test")


@pytest.fixture
def theirs(db):
    return _course("theirs", "them@example.test")


def _sign_in(client, email: str):
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _section(course, title: str, position: int):
    from apps.catalog.models import Section

    return Section.objects.create(course=course, title=title, position=position)


def _sections_url(course) -> str:
    return f"/api/v1/instructor/courses/{course.id}/sections/"


@pytest.mark.django_db
class TestSectionScoping:
    def test_sections_of_another_course_are_not_listed(self, client, mine, theirs) -> None:
        _section(mine, "Mine", 1)
        _section(theirs, "Theirs", 1)
        _sign_in(client, "me@example.test")

        titles = {row["title"] for row in client.get(_sections_url(mine)).json()["results"]}

        assert titles == {"Mine"}

    def test_listing_another_courses_sections_is_a_404(self, client, mine, theirs) -> None:
        _section(theirs, "Theirs", 1)
        _sign_in(client, "me@example.test")

        assert client.get(_sections_url(theirs)).status_code == 404

    def test_adding_a_section_to_another_course_is_a_404(self, client, mine, theirs) -> None:
        from apps.catalog.models import Section

        _sign_in(client, "me@example.test")

        response = client.post(
            _sections_url(theirs),
            {"title": "Injected", "position": 1},
            content_type="application/json",
        )

        assert response.status_code == 404
        assert not Section.objects.filter(course=theirs).exists()


@pytest.mark.django_db
class TestReorder:
    """Abuse case 7."""

    def _reorder(self, client, course, ids):
        return client.post(
            f"{_sections_url(course)}reorder/",
            {"order": [str(i) for i in ids]},
            content_type="application/json",
        )

    def test_reordering_swaps_positions(self, client, mine) -> None:
        """The case the deferrable constraint exists for: the swap passes
        through a state where two sections share a position."""
        first = _section(mine, "First", 1)
        second = _section(mine, "Second", 2)
        _sign_in(client, "me@example.test")

        response = self._reorder(client, mine, [second.id, first.id])

        assert response.status_code == 200
        first.refresh_from_db()
        second.refresh_from_db()
        assert (second.position, first.position) == (1, 2)

    def test_a_row_by_row_swap_needs_the_deferred_constraint(self, mine) -> None:
        """Proves the deferral is load-bearing rather than decoration.

        Not routed through the endpoint on purpose. ``bulk_update`` writes the
        whole permutation in a single UPDATE, and PostgreSQL checks a
        deferrable constraint at end of *statement* even when it is IMMEDIATE —
        so the endpoint currently survives the intermediate state by batching,
        not by deferral. The deferral is what covers the cases batching does
        not: a course with enough sections that ``bulk_update`` splits, and any
        future refactor to per-row saves.

        So the swap is done row by row here, which is the shape the constraint
        actually has to tolerate. Its twin below asserts the same swap fails
        once the constraint is made immediate — without that, this test would
        stay green if someone dropped ``deferrable=`` from the migration, since
        pytest-django never commits and a DEFERRED check never fires.
        """
        from django.db import transaction

        first = _section(mine, "First", 1)
        second = _section(mine, "Second", 2)

        with transaction.atomic():
            first.position = 2
            first.save(update_fields=["position"])
            second.position = 1
            second.save(update_fields=["position"])

        first.refresh_from_db()
        second.refresh_from_db()
        assert (second.position, first.position) == (1, 2)

    def test_the_same_swap_fails_when_the_constraint_is_immediate(self, mine) -> None:
        """The twin. If this stops failing, the constraint stopped deferring."""
        from django.db import IntegrityError, connection, transaction

        first = _section(mine, "First", 1)
        # Position 2 is occupied, so moving `first` on to it is the collision.
        _section(mine, "Second", 2)

        with pytest.raises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            first.position = 2
            first.save(update_fields=["position"])

    def test_a_foreign_id_is_refused_and_nothing_moves(self, client, mine, theirs) -> None:
        """The whole point. A partial reorder that drops the foreign id and
        applies the rest would still leave the caller's course in an order
        they did not ask for."""
        first = _section(mine, "First", 1)
        second = _section(mine, "Second", 2)
        intruder = _section(theirs, "Theirs", 1)
        _sign_in(client, "me@example.test")

        response = self._reorder(client, mine, [second.id, intruder.id, first.id])

        assert response.status_code == 400
        first.refresh_from_db()
        second.refresh_from_db()
        intruder.refresh_from_db()
        assert (first.position, second.position) == (1, 2)
        assert intruder.position == 1

    def test_an_incomplete_order_is_refused(self, client, mine) -> None:
        """Omitting a section would leave it at a position another now holds,
        so the payload must name every one."""
        first = _section(mine, "First", 1)
        _section(mine, "Second", 2)
        _sign_in(client, "me@example.test")

        response = self._reorder(client, mine, [first.id])

        assert response.status_code == 400

    def test_reordering_another_course_is_a_404(self, client, mine, theirs) -> None:
        intruder = _section(theirs, "Theirs", 1)
        _sign_in(client, "me@example.test")

        assert self._reorder(client, theirs, [intruder.id]).status_code == 404


@pytest.mark.django_db
class TestLessons:
    def _lessons_url(self, course) -> str:
        return f"/api/v1/instructor/courses/{course.id}/lessons/"

    def test_a_lesson_inherits_its_course_from_the_url(self, client, mine) -> None:
        """`course` is never taken from the body — that is what keeps a lesson
        from being planted in somebody else's course."""
        from apps.catalog.models import Lesson

        section = _section(mine, "Greetings", 1)
        _sign_in(client, "me@example.test")

        response = client.post(
            self._lessons_url(mine),
            {"section": str(section.id), "slug": "intro", "title": "Intro", "position": 1},
            content_type="application/json",
        )

        assert response.status_code == 201
        assert Lesson.objects.get(slug="intro").course == mine

    def test_a_lesson_cannot_be_added_to_another_courses_section(
        self, client, mine, theirs
    ) -> None:
        """The cross-course case the database constraint cannot express: the
        section must belong to the course in the URL."""
        from apps.catalog.models import Lesson

        foreign_section = _section(theirs, "Theirs", 1)
        _sign_in(client, "me@example.test")

        response = client.post(
            self._lessons_url(mine),
            {"section": str(foreign_section.id), "slug": "intro", "title": "Intro", "position": 1},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert not Lesson.objects.exists()

    def test_lessons_are_not_previews_by_default(self, client, mine) -> None:
        from apps.catalog.models import Lesson

        section = _section(mine, "Greetings", 1)
        _sign_in(client, "me@example.test")

        client.post(
            self._lessons_url(mine),
            {"section": str(section.id), "slug": "intro", "title": "Intro", "position": 1},
            content_type="application/json",
        )

        assert Lesson.objects.get(slug="intro").is_preview is False
