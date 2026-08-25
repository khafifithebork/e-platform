"""Related courses. Abuse case 2, and the ranking rule ADR-020 §6 settled.

Abuse case 2 is case 1 with a second reader, and a second reader is exactly
where the publication rule gets forgotten — nothing about a "you might also
like" strip suggests it is a place drafts could leak from, which is why it has
its own case.

The ranking tests are built so that only the rule under test can decide the
order. That is not decoration: T2 shipped a weighting test that passed with
every weight flattened, because the fixture happened to order correctly by
accident. Each test here has a candidate that would win on some *other* signal.
"""

from __future__ import annotations

import pytest

from apps.catalog.selectors import RELATED_LIMIT

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _course(slug: str, *, code="es", level="A1", skills=None, published=True, days_ago=0):
    from datetime import timedelta

    from django.utils import timezone

    from apps.accounts.models import Role
    from apps.accounts.services import create_account
    from apps.catalog.models import Course, CourseStatus, Language

    language, _ = Language.objects.get_or_create(
        code=code, defaults={"name": code.upper(), "native_name": code.upper()}
    )
    instructor = create_account(email=f"{slug}@example.test", password=PASSWORD)
    instructor.role = Role.INSTRUCTOR
    instructor.save(update_fields=["role"])

    course = Course.objects.create(
        slug=slug,
        title=slug.replace("-", " ").title(),
        language=language,
        level=level,
        skill_areas=skills or [],
        instructor=instructor,
    )
    if published:
        Course.objects.filter(pk=course.pk).update(
            status=CourseStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=days_ago),
        )
    course.refresh_from_db()
    return course


def _related(course) -> list[str]:
    from apps.catalog.selectors import related_courses

    return [item.slug for item in related_courses(course=course)]


class TestTheRule:
    def test_same_language_only(self) -> None:
        """A hard filter, not a rank. A learner studying Spanish shown a French
        course has been given a row of things they cannot use."""
        subject = _course("subject", code="es")
        _course("same-language", code="es")
        _course("other-language", code="fr")

        assert _related(subject) == ["same-language"]

    def test_more_shared_skill_areas_ranks_higher(self) -> None:
        """The candidate with fewer shared areas is published *more recently*,
        so recency alone would put it first."""
        subject = _course("subject", skills=["grammar", "listening"])
        _course("shares-two", skills=["grammar", "listening"], days_ago=30)
        _course("shares-one", skills=["grammar"], days_ago=0)

        assert _related(subject)[0] == "shares-two"

    def test_then_the_same_level(self) -> None:
        """Both share nothing, so only level can decide — and the wrong-level
        candidate is the more recent one."""
        subject = _course("subject", level="B1")
        _course("same-level", level="B1", days_ago=30)
        _course("other-level", level="C1", days_ago=0)

        assert _related(subject)[0] == "same-level"

    def test_then_the_most_recent(self) -> None:
        """The tiebreak, and it exists so the strip is deterministic rather
        than whatever order the database felt like."""
        subject = _course("subject", level="B1", skills=["grammar"])
        _course("older", level="B1", skills=["grammar"], days_ago=30)
        _course("newer", level="B1", skills=["grammar"], days_ago=1)

        assert _related(subject) == ["newer", "older"]

    def test_a_course_is_never_related_to_itself(self) -> None:
        subject = _course("subject")
        _course("other")

        assert "subject" not in _related(subject)

    def test_a_course_with_no_skill_areas_still_gets_a_strip(self) -> None:
        """The empty-overlap branch. Ranking rests on level and recency, which
        is better than showing nothing."""
        subject = _course("subject", skills=[], level="B1")
        _course("same-level", level="B1")

        assert _related(subject) == ["same-level"]

    def test_it_is_capped(self) -> None:
        subject = _course("subject")
        for index in range(RELATED_LIMIT + 4):
            _course(f"other-{index}")

        assert len(_related(subject)) == RELATED_LIMIT


class TestItNeverSurfacesWhatIsNotPublished:
    """Abuse case 2."""

    def test_a_draft_is_not_related(self) -> None:
        subject = _course("subject", skills=["grammar"])
        _course("secret-draft", skills=["grammar"], published=False)
        _course("public-one", skills=["grammar"])

        assert _related(subject) == ["public-one"]

    def test_an_archived_course_drops_out(self) -> None:
        from apps.accounts.models import Role
        from apps.accounts.services import create_account
        from apps.catalog.services import archive

        subject = _course("subject", skills=["grammar"])
        other = _course("public-one", skills=["grammar"])
        assert _related(subject) == ["public-one"]

        admin = create_account(email="admin@example.test", password=PASSWORD)
        admin.role = Role.ADMIN
        admin.save(update_fields=["role"])
        archive(course=other, by=admin)

        assert _related(subject) == []

    def test_the_selector_does_not_roll_its_own_filter(self) -> None:
        """Structural, in the strong form: `Course.objects` must appear
        nowhere. The weak version — asserting only that `published_courses` is
        called — passed in T3 while drafts were being returned."""
        import ast
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "apps" / "catalog" / "selectors.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "related_courses"
        )

        called = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attribute_chains = {
            f"{node.value.id}.{node.attr}"
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        }

        assert "published_courses" in called
        assert "Course.objects" not in attribute_chains


class TestOnTheDetailResponse:
    def test_the_detail_page_carries_them(self, client) -> None:
        subject = _course("subject", skills=["grammar"])
        _course("neighbour", skills=["grammar"])

        body = client.get(f"/api/v1/catalogue/courses/{subject.slug}/").json()

        assert [item["slug"] for item in body["related"]] == ["neighbour"]

    def test_they_are_cards_rather_than_full_details(self, client) -> None:
        """A related course rendering its own curriculum and its own related
        courses would recurse, and a strip of cards needs neither."""
        subject = _course("subject", skills=["grammar"])
        _course("neighbour", skills=["grammar"])

        related = client.get(f"/api/v1/catalogue/courses/{subject.slug}/").json()["related"][0]

        assert "sections" not in related
        assert "related" not in related

    def test_a_draft_never_appears_there_either(self, client) -> None:
        """Through the API as well as the selector. The endpoint is the surface
        an attacker actually has."""
        subject = _course("subject", skills=["grammar"])
        _course("secret-draft", skills=["grammar"], published=False)

        body = client.get(f"/api/v1/catalogue/courses/{subject.slug}/").json()

        assert body["related"] == []

    def test_it_costs_a_fixed_number_of_queries(self, client) -> None:
        """ADR-009's form: two dataset sizes, identical counts. A related strip
        resolved per candidate is the classic N+1, and it is invisible until
        the catalogue has depth."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        subject = _course("subject", skills=["grammar"])
        url = f"/api/v1/catalogue/courses/{subject.slug}/"

        _course("first", skills=["grammar"])
        with CaptureQueriesContext(connection) as small:
            assert client.get(url).status_code == 200

        for index in range(5):
            _course(f"more-{index}", skills=["grammar"])
        with CaptureQueriesContext(connection) as large:
            assert client.get(url).status_code == 200

        assert len(large.captured_queries) == len(small.captured_queries), (
            f"{len(small.captured_queries)} queries for 1 related, "
            f"{len(large.captured_queries)} for 6"
        )
