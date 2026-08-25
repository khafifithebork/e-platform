"""Searching the catalogue. Abuse cases 1, 3, 5 and 6.

The case that matters most is 1, and it has a positive twin: a filter matching
nothing would satisfy "search never returns a draft" perfectly and ship a
search box that finds nothing. So every negative here is paired with a
published course that *is* found.

Abuse case 5 is the one that is easy to write badly. A pathological query is
not only a long one — an unbalanced parenthesis is what turns `to_tsquery`
into a 500, and the reason this uses `websearch_to_tsquery` instead.
"""

from __future__ import annotations

import pytest

from apps.catalog.selectors import MAX_QUERY_LENGTH, SEARCH_LIMIT

PASSWORD = "a-long-enough-passphrase"
URL = "/api/v1/catalogue/search/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _instructor(email: str):
    from apps.accounts.models import Role
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.INSTRUCTOR
    user.save(update_fields=["role"])
    return user


def _course(slug: str, title: str, *, published: bool = True, **overrides):
    """A course, refreshed, and published unless asked otherwise.

    Publication goes through the real services so that `published_at` and the
    check constraint are satisfied the way production satisfies them.
    """
    from django.utils import timezone

    from apps.catalog.models import Course, CourseStatus, Language
    from apps.catalog.services import refresh_search_vector

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Espanol"}
    )
    course = Course.objects.create(
        slug=slug,
        title=title,
        description=overrides.pop("description", ""),
        skill_areas=overrides.pop("skill_areas", []),
        level=overrides.pop("level", "A1"),
        language=language,
        instructor=_instructor(f"{slug}@example.test"),
    )
    if published:
        Course.objects.filter(pk=course.pk).update(
            status=CourseStatus.PUBLISHED, published_at=timezone.now()
        )
        course.refresh_from_db()
    refresh_search_vector(course=course)
    return course


def _search(client, query: str):
    return client.get(URL, {"q": query})


class TestItFindsPublishedCourses:
    def test_a_word_in_the_title(self, client) -> None:
        _course("spanish", "Spanish for Beginners")

        body = _search(client, "spanish").json()

        assert [item["slug"] for item in body["results"]] == ["spanish"]

    def test_a_word_in_the_description(self, client) -> None:
        _course("misc", "General Course", description="Focused on pronunciation drills.")

        body = _search(client, "pronunciation").json()

        assert [item["slug"] for item in body["results"]] == ["misc"]

    def test_a_skill_area(self, client) -> None:
        _course("skills", "General Course", skill_areas=["listening", "grammar"])

        body = _search(client, "grammar").json()

        assert [item["slug"] for item in body["results"]] == ["skills"]

    def test_an_anonymous_visitor_may_search(self, client) -> None:
        """The catalogue is the only unauthenticated product surface, and
        search is part of it. `AllowAny` is an exemption, so it is tested."""
        _course("spanish", "Spanish for Beginners")

        assert _search(client, "spanish").status_code == 200


class TestItNeverReturnsWhatIsNotPublished:
    """Abuse case 1, each half paired with its positive twin — a search that
    found nothing at all would satisfy every negative here."""

    def test_a_draft_is_invisible(self, client) -> None:
        _course("draft-course", "Spanish Drafting", published=False)
        _course("live-course", "Spanish Living")

        slugs = [item["slug"] for item in _search(client, "spanish").json()["results"]]

        assert slugs == ["live-course"]

    def test_an_archived_course_disappears(self, client) -> None:
        """Driven through the real transition, not by setting a column: the
        question is whether archiving removes it from search, and a test that
        wrote the status directly would not prove the service does."""
        from apps.accounts.models import Role
        from apps.accounts.services import create_account
        from apps.catalog.services import archive

        course = _course("live-course", "Spanish Living")
        assert _search(client, "spanish").json()["count"] == 1

        admin = create_account(email="admin@example.test", password=PASSWORD)
        admin.role = Role.ADMIN
        admin.save(update_fields=["role"])
        archive(course=course, by=admin)

        assert _search(client, "spanish").json()["count"] == 0

    def test_it_reads_through_the_one_publication_filter(self) -> None:
        """Structural. `search_published_courses` must build on
        `published_courses()`, which is the single place the publication rule
        lives — a hand-rolled `filter(status=...)` here is a second rule that
        drifts from the first the day one of them changes."""
        import ast
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "apps" / "catalog" / "selectors.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "search_published_courses"
        )

        called = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        # Keyword arguments only. A first version dumped the whole node and
        # searched the text for "status", which matched the function's own
        # docstring — it passed for the wrong reason and would have kept
        # passing over a hand-rolled filter.
        filtered_on = {
            keyword.arg
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg
        }

        # `Course.objects` must not appear at all. Asserting only that
        # `published_courses` is called is too weak: replacing one of the two
        # branches with `Course.objects.all()` left the other call in place and
        # this test passed while drafts were being returned. The behavioural
        # tests above caught it; this one is supposed to.
        attribute_chains = {
            f"{node.value.id}.{node.attr}"
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        }

        assert "published_courses" in called
        assert "Course.objects" not in attribute_chains
        assert not {name for name in filtered_on if name.startswith("status")}


class TestWhatASearchResultShows:
    def test_it_carries_no_lesson_bodies(self, client) -> None:
        """Abuse case 3. The public serializer has no `body` field at all
        (ADR-008 §6), and search must not have quietly picked a richer one."""
        _course("spanish", "Spanish for Beginners")

        body = _search(client, "spanish").json()

        assert "body" not in str(body)
        assert "search_vector" not in str(body)

    def test_it_says_when_it_was_capped(self, client) -> None:
        """ADR-020 §4. A client that cannot tell a full list from a cut one
        renders "50 results" as though it were all of them."""
        body = _search(client, "spanish").json()

        assert body["limit"] == SEARCH_LIMIT
        assert body["truncated"] is False

    def test_the_cap_is_enforced(self, client) -> None:
        for index in range(SEARCH_LIMIT + 3):
            _course(f"course-{index}", "Spanish Basics")

        body = _search(client, "spanish").json()

        assert body["count"] == SEARCH_LIMIT
        assert body["truncated"] is True


class TestTheTrigramFallback:
    def test_a_typo_still_finds_the_course(self, client) -> None:
        _course("spanish", "Spanish")

        body = _search(client, "spanich").json()

        assert [item["slug"] for item in body["results"]] == ["spanish"]

    def test_it_does_not_run_when_full_text_matched(self, client) -> None:
        """ADR-020 §5: the fallback fires only on zero rows. If it were unioned
        in, this search would also return the fuzzy neighbour."""
        _course("spanish", "Spanish")
        _course("spanich-typo", "Spanich")

        slugs = [item["slug"] for item in _search(client, "spanish").json()["results"]]

        assert slugs == ["spanish"]

    def test_nonsense_still_finds_nothing(self, client) -> None:
        """The twin. A fallback with no threshold returns the whole catalogue
        for any input, and every test above would still pass."""
        _course("spanish", "Spanish")

        assert _search(client, "zzzzqqqqxxxx").json()["count"] == 0


class TestPathologicalInput:
    """Abuse case 5."""

    def test_an_empty_query_returns_nothing_rather_than_everything(self, client) -> None:
        _course("spanish", "Spanish for Beginners")

        assert _search(client, "").json()["count"] == 0

    def test_a_missing_query_parameter_is_not_an_error(self, client) -> None:
        assert client.get(URL).status_code == 200

    @pytest.mark.parametrize(
        "query",
        [
            "spanish & | ! ( )",
            "((((",
            "'unbalanced",
            "spanish:*",
            "\x00\x01\x02",
        ],
    )
    def test_operator_soup_does_not_raise(self, client, query: str) -> None:
        """`websearch_to_tsquery` never raises on malformed input; `to_tsquery`
        does, and an unbalanced parenthesis from a visitor would be a 500."""
        assert _search(client, query).status_code == 200

    def test_a_very_long_query_is_bounded(self, client) -> None:
        """Truncated rather than rejected: a 400 teaches nobody anything, and
        the first 200 characters of a runaway paste are still a real search."""
        _course("spanish", "Spanish for Beginners")

        response = _search(client, "spanish " + ("x" * 50_000))

        assert response.status_code == 200

    def test_the_bound_is_actually_applied(self, client) -> None:
        """The twin. Without it the test above passes over an unbounded query
        that Postgres happened to survive."""
        from apps.catalog.selectors import search_published_courses

        course = _course("spanish", "Spanish")

        # The word sits beyond the cut, so a bounded query cannot match it.
        assert search_published_courses(query=("x " * MAX_QUERY_LENGTH) + "spanish") == []
        assert search_published_courses(query="spanish") == [course]


class TestItIsThrottled:
    def test_search_has_its_own_scope(self, settings) -> None:
        """Abuse case 6. Ranked full text over a GIN index is the most
        expensive thing an anonymous visitor can ask for, and the catalogue
        scope is sized for browsing several pages a minute."""
        from apps.catalog.public_views import CourseSearchView

        assert CourseSearchView.throttle_scope == "search"
        assert "search" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    # Enforcement is proven in `test_throttling.py`, not here. This module
    # raises every rate to 10000/hour, and DRF binds `THROTTLE_RATES` as a
    # class attribute when `rest_framework.throttling` is first imported — a
    # per-test override in this file never takes effect and reads exactly like
    # a passing test over an inert throttle. That trap is documented in
    # `TestUploadUrlsAreRationed`; this is the second time it has been walked
    # into.
