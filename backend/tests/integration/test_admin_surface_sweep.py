"""Abuse cases 1 and 9, swept rather than spot-checked.

Both were covered by hand before this: three per-route permission classes for
case 1, and four listed URLs for case 9. Hand-written coverage of a *set* has
one failure mode, and it is the one this codebase keeps finding — it covers
what existed when somebody wrote it. T8 added an `/admin-api/` route and the
inventory guard caught it precisely because that guard enumerates. These do the
same for permissions and for the path.

Each sweep has a twin asserting the sweep found something. A sweep over an
empty enumeration passes forever and reads as thorough, which is worse than no
test at all.
"""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.urls import URLPattern, URLResolver, clear_url_caches, get_resolver

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"
ADMIN_PATH = "staff-console-test"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def routed(settings):
    """Route the admin for one test, then put it back.

    Same shape as `test_admin_site_routing.py`, where the reason the module has
    to be reloaded on the way in *and* out is written out in full.
    """
    from config import urls as url_conf

    settings.ADMIN_PATH = ADMIN_PATH
    importlib.reload(url_conf)
    clear_url_caches()
    yield ADMIN_PATH

    settings.ADMIN_PATH = ""
    importlib.reload(url_conf)
    clear_url_caches()


def _user(email: str, *, role: str = Role.STUDENT, staff: bool = False):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.is_staff = staff
    user.save(update_fields=["role", "is_staff"])
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


_PARAMETERS = {
    "uuid": lambda: str(uuid.uuid4()),
    "int": lambda: "1",
    "slug": lambda: "a-slug",
    "str": lambda: "something",
}


def _concrete(route: str) -> str | None:
    """Turn `users/<uuid:pk>/refund/` into a URL that can actually be requested.

    Returns None for a route using a converter this does not know, so a new
    converter shows up as a route the sweep skipped rather than as a URL it
    silently got wrong. The twin below is what turns that into a failure.
    """
    out = []
    for segment in route.split("/"):
        if segment.startswith("<") and segment.endswith(">"):
            converter = segment[1:-1].split(":")[0]
            if converter not in _PARAMETERS:
                return None
            out.append(_PARAMETERS[converter]())
        else:
            out.append(segment)
    return "/".join(out)


def _routes() -> list[str]:
    """Every full route string the URL conf serves."""
    found: list[str] = []

    def walk(patterns, prefix: str) -> None:
        for entry in patterns:
            route = getattr(entry.pattern, "_route", None)
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns, prefix + (route or ""))
            elif isinstance(entry, URLPattern) and route is not None:
                found.append(prefix + route)

    walk(get_resolver().url_patterns, "")
    return found


def _admin_api_routes() -> list[str]:
    return [route for route in _routes() if "admin-api/" in route]


def _admin_api_urls() -> list[str]:
    """Requestable URLs only.

    A route whose converter `_concrete` does not understand is skipped here and
    reported by `test_the_sweep_covers_every_routed_endpoint`, which fails on
    its own claim. The alternative — letting the loops build `"/" + None` —
    fails every sweep at once with a `TypeError`, and a test whose failure mode
    is a crash says less than one that fails on what it asserts.
    """
    urls = []
    for route in _admin_api_routes():
        concrete = _concrete(route)
        if concrete is not None:
            urls.append("/" + concrete)
    return urls


class TestEveryAdminApiRouteRefusesANonAdmin:
    """Abuse case 1, first half.

    Driven with a random id, deliberately. T8 proved the permission class
    answers before the object is looked up, so a non-admin gets the same
    refusal whether or not the row exists — which is the property being swept.
    """

    @pytest.mark.parametrize(
        ("email", "role", "staff"),
        [
            ("student@example.test", Role.STUDENT, False),
            ("teacher@example.test", Role.INSTRUCTOR, False),
            ("staffer@example.test", Role.STUDENT, True),
        ],
    )
    def test_a_signed_in_non_admin_is_refused_everywhere(
        self, client, db, email: str, role: str, staff: bool
    ) -> None:
        _user(email, role=role, staff=staff)
        _sign_in(client, email)

        for url in _admin_api_urls():
            assert client.get(url).status_code == 403, f"GET {url}"
            posted = client.post(url, {}, content_type="application/json")
            assert posted.status_code == 403, f"POST {url}"

    def test_an_anonymous_caller_is_refused_everywhere(self, client, db) -> None:
        for url in _admin_api_urls():
            assert client.get(url).status_code in (401, 403), f"GET {url}"

    def test_an_administrator_is_not_refused(self, client, db) -> None:
        """The positive twin. A boundary that refused everybody would satisfy
        every assertion above and serve nobody."""
        _user("admin@example.test", role=Role.ADMIN)
        _sign_in(client, "admin@example.test")

        refused = [url for url in _admin_api_urls() if client.get(url).status_code == 403]

        assert refused == []

    def test_the_sweep_covers_every_routed_endpoint(self) -> None:
        """The twin that matters. A sweep over an empty list passes forever.

        Asserted as "every admin-api route produced a URL" rather than against
        a hardcoded count, so adding a route does not mean editing a number —
        but a route using an unknown converter fails here rather than being
        quietly skipped.
        """
        routes = _admin_api_routes()

        assert routes, "the sweep enumerated no admin-api routes at all"
        assert all(_concrete(route) is not None for route in routes)


class TestThePathIsInNothingWeServe:
    """Abuse case 9, swept. The spec asks for exactly that word.

    Obscurity is worth precisely as much as the path staying unknown, so the
    question is not whether four chosen endpoints leak it — it is whether
    anything does.
    """

    @staticmethod
    def _sweepable(routed: str) -> list[str]:
        """Every route we can request, minus the admin site's own pages.

        The admin's own responses contain its path by construction; including
        them would be asserting that the site does not exist.
        """
        urls = []
        for route in _routes():
            if route.startswith(routed):
                continue
            concrete = _concrete(route)
            if concrete is not None:
                urls.append("/" + concrete)
        return urls

    def test_no_response_contains_it_anonymously(self, client, routed) -> None:
        for url in self._sweepable(routed):
            assert routed.encode() not in client.get(url).content, url

    def test_nor_when_an_administrator_is_signed_in(self, client, routed) -> None:
        """Signed in is the case worth sweeping: a serializer that rendered a
        reversed admin URL would do it for the person who has one."""
        _user("admin@example.test", role=Role.ADMIN, staff=True)
        _sign_in(client, "admin@example.test")

        for url in self._sweepable(routed):
            assert routed.encode() not in client.get(url).content, url

    def test_nor_a_404(self, client, routed) -> None:
        """Where a path most plausibly leaks. Django's *debug* 404 lists every
        URL pattern it tried, admin included — `DEBUG` is False here and in
        production, and this is the test that says so rather than assuming it.
        """
        response = client.get("/no-such-page-anywhere/")

        assert response.status_code == 404
        assert routed.encode() not in response.content

    def test_nor_a_refusal(self, client, routed) -> None:
        _user("student@example.test")
        _sign_in(client, "student@example.test")

        response = client.get(f"/api/v1/admin-api/users/{uuid.uuid4()}/diagnostics/")

        assert response.status_code == 403
        assert routed.encode() not in response.content

    def test_nor_the_openapi_schema(self, client, routed) -> None:
        response = client.get("/api/v1/schema/")

        assert response.status_code == 200
        assert routed.encode() not in response.content

    def test_the_sweep_visited_something(self, routed) -> None:
        """The twin. Every assertion above is a negative, and a sweep over an
        empty list of URLs proves nothing at all."""
        assert len(self._sweepable(routed)) > 10

    def test_and_the_needle_would_be_found_if_it_were_there(self, client, routed) -> None:
        """The second twin, for the needle rather than the haystack. A
        misspelled path would make every assertion above pass over any response
        whatsoever."""
        response = client.get(f"/{routed}/", follow=True)

        assert routed.encode() in response.request["PATH_INFO"].encode()
