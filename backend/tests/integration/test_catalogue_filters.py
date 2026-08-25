"""Narrowing the catalogue. Abuse case 4.

The case says filters must not be combinable into a way past publication
scoping, and it says *swept, not spot-checked*. So `TestNoCombinationIsAWayIn`
generates every combination of the three parameters and asserts a draft appears
in none of them — a hand-picked pair would cover what somebody thought of on
the day.

The other thing being pinned here is that an unrecognised value is a 400. The
tempting behaviour is to ignore it, which returns the whole catalogue and reads
to the caller exactly like a filter that matched everything.
"""

from __future__ import annotations

import itertools
from typing import ClassVar

import pytest

PASSWORD = "a-long-enough-passphrase"
URL = "/api/v1/catalogue/courses/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _course(slug: str, *, code="es", level="A1", skills=None, published=True):
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
            status=CourseStatus.PUBLISHED, published_at=timezone.now()
        )
    return course


def _slugs(client, **params) -> list[str]:
    response = client.get(URL, params)
    assert response.status_code == 200, response.content
    return [item["slug"] for item in response.json()["results"]]


class TestEachFilterNarrows:
    def test_by_language(self, client) -> None:
        _course("spanish-one", code="es")
        _course("french-one", code="fr")

        assert _slugs(client, language="es") == ["spanish-one"]

    def test_by_level(self, client) -> None:
        _course("beginner", level="A1")
        _course("advanced", level="C1")

        assert _slugs(client, level="C1") == ["advanced"]

    def test_by_skill_area(self, client) -> None:
        _course("listening-course", skills=["listening", "grammar"])
        _course("writing-course", skills=["writing"])

        assert _slugs(client, skill_area="listening") == ["listening-course"]

    def test_they_compose(self, client) -> None:
        _course("wanted", code="es", level="B1", skills=["grammar"])
        _course("wrong-level", code="es", level="A1", skills=["grammar"])
        _course("wrong-language", code="fr", level="B1", skills=["grammar"])
        _course("wrong-skill", code="es", level="B1", skills=["writing"])

        found = _slugs(client, language="es", level="B1", skill_area="grammar")

        assert found == ["wanted"]

    def test_no_filter_returns_everything_published(self, client) -> None:
        """The positive twin for the whole file. Filters that matched nothing
        would satisfy every narrowing assertion above."""
        _course("one")
        _course("two")

        assert sorted(_slugs(client)) == ["one", "two"]


class TestAnUnrecognisedValueIsRefused:
    def test_an_unknown_level(self, client) -> None:
        _course("beginner", level="A1")

        assert client.get(URL, {"level": "Z9"}).status_code == 400

    def test_an_unknown_language(self, client) -> None:
        _course("spanish-one", code="es")

        assert client.get(URL, {"language": "xx"}).status_code == 400

    def test_rather_than_returning_the_whole_catalogue(self, client) -> None:
        """The failure this prevents, stated as its own test. A dropped filter
        is indistinguishable from one that matched everything, and the day a
        typo starts showing every course, nothing reports it."""
        _course("a", level="A1")
        _course("b", level="C1")

        response = client.get(URL, {"level": "Z9"})

        assert response.status_code == 400
        assert "results" not in response.json()

    def test_but_an_unknown_parameter_name_is_ignored(self, client) -> None:
        """Deliberately different. Adding a tracking parameter to a URL must
        not break the page."""
        _course("one")

        assert _slugs(client, utm_source="newsletter") == ["one"]

    def test_and_a_blank_value_is_not_a_filter(self, client) -> None:
        """`?language=` is what an empty form control sends."""
        _course("one")

        assert _slugs(client, language="", level="", skill_area="") == ["one"]


class TestNoCombinationIsAWayIn:
    """Abuse case 4, swept.

    Every combination of the three parameters, against a catalogue holding one
    draft and one published course that are otherwise identical. A pair chosen
    by hand covers what somebody thought of on the day; this covers the set.
    """

    PARAMETERS: ClassVar[dict[str, str]] = {
        "language": "es",
        "level": "B1",
        "skill_area": "grammar",
    }

    @staticmethod
    def _combinations():
        names = list(TestNoCombinationIsAWayIn.PARAMETERS)
        for size in range(len(names) + 1):
            for chosen in itertools.combinations(names, size):
                yield {name: TestNoCombinationIsAWayIn.PARAMETERS[name] for name in chosen}

    def test_a_draft_appears_under_no_filter_combination(self, client) -> None:
        _course("secret-draft", code="es", level="B1", skills=["grammar"], published=False)
        _course("public-one", code="es", level="B1", skills=["grammar"])

        for params in self._combinations():
            found = _slugs(client, **params)
            assert "secret-draft" not in found, params

    def test_and_the_published_twin_appears_under_all_of_them(self, client) -> None:
        """The twin, and the reason the sweep above means anything. Filters
        that excluded everything would pass it perfectly."""
        _course("secret-draft", code="es", level="B1", skills=["grammar"], published=False)
        _course("public-one", code="es", level="B1", skills=["grammar"])

        for params in self._combinations():
            found = _slugs(client, **params)
            assert found == ["public-one"], params

    def test_the_sweep_covers_more_than_one_case(self) -> None:
        """A sweep over an empty generator passes forever."""
        assert len(list(self._combinations())) == 8


class TestFilteringReadsThroughTheOnePublicationFilter:
    def test_the_selector_does_not_roll_its_own(self) -> None:
        """Structural, and written to fail when it should: it asserts
        `Course.objects` appears nowhere, not merely that `published_courses`
        is called somewhere. T3 shipped the weaker version and it passed while
        drafts were being returned."""
        import ast
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "apps" / "catalog" / "selectors.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "filtered_published_courses"
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
