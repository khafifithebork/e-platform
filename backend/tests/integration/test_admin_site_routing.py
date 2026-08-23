"""Routing the Django admin, and who gets in.

architecture.md §8 calls Django Admin production infrastructure and the
highest-value target in the system. It has been unrouted since M0 for exactly
that reason; this is the milestone that routes it, so these tests are about the
exposure that creates.

**Obscurity is not the control here** and the tests are arranged to say so:
the path being unguessable keeps scanners away, and `is_staff` is what actually
refuses people. Abuse case 2's 2FA arrives in T6 and is the third layer.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import clear_url_caches

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
    """Route the admin for one test.

    The URL conf is built at import and cached, so changing the setting is not
    enough — the module has to be reloaded and `clear_url_caches` called, both
    on the way in and on the way out. Without the second half every later test
    in the process would see an admin site that its own settings say is not
    there.
    """
    import importlib

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


class TestItIsOnlyThereWhenConfigured:
    def test_an_unset_path_routes_nothing(self, client, settings) -> None:
        """The default. An environment that has not chosen a path gets no
        admin site — not one at a location this repository would have had to
        publish in order to default to it."""
        assert settings.ADMIN_PATH == ""

        assert client.get("/admin/").status_code == 404

    def test_a_configured_path_serves_the_login(self, client, routed) -> None:
        """The twin. Every test in this file would pass over an admin site that
        was never routed at all."""
        response = client.get(f"/{routed}/", follow=True)

        assert response.status_code == 200
        assert b"password" in response.content.lower()

    def test_the_default_path_is_still_nothing(self, client, routed) -> None:
        """Routed elsewhere means `/admin/` stays a 404, which is the whole
        point of moving it."""
        assert client.get("/admin/").status_code == 404


class TestOnlyStaffGetIn:
    """`force_login`, not `login`: django-axes refuses to authenticate without
    a request object, and these are about authorisation rather than the login
    flow — which `test_login.py` already covers."""

    def test_a_learner_is_refused(self, client, routed) -> None:
        client.force_login(_user("learner@example.test"))

        response = client.get(f"/{routed}/", follow=True)

        assert b"dashboard" not in response.content.lower()
        assert b"password" in response.content.lower()

    def test_an_administrator_by_role_is_refused(self, client, routed) -> None:
        """The distinction M3 drew, arriving where it matters.

        `role == ADMIN` grants the admin *API* — diagnostics, overrides. It
        does not grant the Django admin site, which is a wider capability over
        every table. `is_staff` is granted deliberately and separately, and
        this test is what stops the two quietly merging.
        """
        client.force_login(_user("roleadmin@example.test", role=Role.ADMIN))

        response = client.get(f"/{routed}/", follow=True)

        assert b"password" in response.content.lower()

    def test_staff_get_in(self, client, routed) -> None:
        """The positive twin. Without it, an admin site that refused everybody
        would satisfy both tests above."""
        client.force_login(_user("staff@example.test", role=Role.ADMIN, staff=True))

        response = client.get(f"/{routed}/")

        assert response.status_code == 200
        assert b"site-name" in response.content or b"Site administration" in response.content

    def test_an_inactive_staff_member_is_refused(self, client, routed) -> None:
        user = _user("gone@example.test", role=Role.ADMIN, staff=True)
        client.force_login(user)
        user.is_active = False
        user.save(update_fields=["is_active"])

        response = client.get(f"/{routed}/", follow=True)

        assert b"password" in response.content.lower()


class TestThePathDoesNotLeak:
    """Abuse case 9. Obscurity is a weak control and worth exactly as much as
    the path staying unknown, so nothing we serve may contain it."""

    def test_it_is_absent_from_the_openapi_schema(self, client, routed) -> None:
        response = client.get("/api/v1/schema/")

        assert response.status_code == 200
        assert routed.encode() not in response.content

    def test_it_is_absent_from_every_public_response(self, client, routed) -> None:
        for url in (
            "/api/v1/catalogue/courses/",
            "/api/v1/catalogue/languages/",
            "/healthz",
            "/api/v1/auth/me/",
        ):
            assert routed.encode() not in client.get(url).content, url

    def test_the_check_can_see_the_path_when_it_is_present(self, client, routed) -> None:
        """The twin for a negative assertion: a misspelled needle would make
        both tests above pass over any response at all."""
        response = client.get(f"/{routed}/", follow=True)

        assert routed.encode() in response.request["PATH_INFO"].encode()


class TestTheGuessablePathCheck:
    @pytest.mark.parametrize("path", ["admin", "ADMIN", "django-admin", "dashboard"])
    def test_an_obvious_path_is_an_error(self, path: str) -> None:
        from apps.core.checks import check_admin_path

        with override_settings(ADMIN_PATH=path):
            errors = check_admin_path(None)

        assert [error.id for error in errors] == ["core.E001"]

    def test_an_unguessable_path_is_accepted(self) -> None:
        """The twin. A check that errored on everything would pass the test
        above and make the setting unusable."""
        from apps.core.checks import check_admin_path

        with override_settings(ADMIN_PATH="staff-console-9f2a"):
            assert check_admin_path(None) == []

    def test_no_path_at_all_is_accepted(self) -> None:
        """Unrouted is the safe state, not a misconfiguration."""
        from apps.core.checks import check_admin_path

        with override_settings(ADMIN_PATH=""):
            assert check_admin_path(None) == []
