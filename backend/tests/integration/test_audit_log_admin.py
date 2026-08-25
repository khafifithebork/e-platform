"""The audit log is readable in the admin site, and nothing else. Abuse case 6.

ADR-018 §6 promised this registration and T2 did not ship it, so until now the
model was absent from the admin entirely — abuse case 6 passed because there
was no surface to edit through, which is a different fact from the one it was
written to assert.

Append-only is already enforced on the model and the queryset, with tests in
`tests/unit/test_audit_log.py`. This file is about the *surface*: a `ModelAdmin`
with the defaults on offers add, change, delete and a bulk-delete action, and a
button whose handler raises is a worse answer than a page that never offered
it.

`test_the_bulk_delete_action_is_absent` is the one worth reading. Denying
`has_delete_permission` does **not** remove `delete_selected` in every Django
configuration — it comes from the site's action registry, not the ModelAdmin's
permissions — so the two controls are asserted separately.
"""

from __future__ import annotations

import importlib

import pytest
from django.contrib import admin as django_admin
from django.test import Client
from django.urls import clear_url_caches

from apps.accounts.models import Role
from apps.core.audit import AdminAction, record_admin_action
from apps.core.models import AuditLog
from tests.otp_helpers import verify_admin_session

PASSWORD = "a-long-enough-passphrase"
ADMIN_PATH = "staff-console-test"

pytestmark = pytest.mark.django_db


@pytest.fixture
def routed(settings):
    """Route the admin for one test, then put it back.

    The URL conf is built at import and cached, so the module has to be
    reloaded on the way in *and* on the way out — copied from
    `test_admin_site_routing.py`, where the reason is written out in full.
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
    """Staff accounts are superusers here, the same choice
    `test_admin_review_queue.py` makes and for the same reason: the admin index
    only lists models the account holds permissions for, and this file is about
    what the ModelAdmin refuses, not about Django's permission plumbing."""
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.is_staff = staff
    user.is_superuser = staff
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    return user


@pytest.fixture
def staff(db):
    return _user("staff@example.test", role=Role.ADMIN, staff=True)


@pytest.fixture
def row(db, staff) -> AuditLog:
    return record_admin_action(
        actor=staff,
        action=AdminAction.ACCESS_OVERRIDE_GRANTED,
        target=_user("learner@example.test"),
        reason="Double charged in July",
        days=14,
    )


@pytest.fixture
def signed_in(client: Client, staff, routed):
    client.force_login(staff)
    verify_admin_session(client, "staff@example.test")
    return client


class TestItIsReadable:
    def test_the_changelist_lists_the_row(self, signed_in, row, routed) -> None:
        response = signed_in.get(f"/{routed}/core/auditlog/")

        assert response.status_code == 200
        assert b"ACCESS_OVERRIDE_GRANTED" in response.content

    def test_the_detail_view_shows_the_whole_row(self, signed_in, row, routed) -> None:
        """Including `metadata`, which the diagnostics API deliberately does
        not render. This is the surface for detail; that one is a summary."""
        response = signed_in.get(f"/{routed}/core/auditlog/{row.pk}/change/")

        assert response.status_code == 200
        assert b"Double charged in July" in response.content


class TestItIsNotWritable:
    def test_adding_is_refused(self, signed_in, routed) -> None:
        assert signed_in.get(f"/{routed}/core/auditlog/add/").status_code == 403

    def test_changing_is_refused(self, signed_in, row, routed) -> None:
        """The detail page renders, and a POST to it changes nothing."""
        response = signed_in.post(
            f"/{routed}/core/auditlog/{row.pk}/change/",
            {"action": "TAMPERED", "actor_label": "someone.else@example.test"},
        )

        assert response.status_code in (403, 302)
        row.refresh_from_db()
        assert row.action == AdminAction.ACCESS_OVERRIDE_GRANTED
        assert row.actor_label == "staff@example.test"

    def test_deleting_is_refused(self, signed_in, row, routed) -> None:
        response = signed_in.post(f"/{routed}/core/auditlog/{row.pk}/delete/")

        assert response.status_code in (403, 302)
        assert AuditLog.objects.filter(pk=row.pk).exists()

    def test_the_bulk_delete_action_is_absent(self) -> None:
        """`has_delete_permission` alone does not necessarily remove it —
        `delete_selected` comes from the site's action registry. Asserted
        against the registered ModelAdmin rather than by scraping HTML, so it
        cannot pass because a template happened to render differently."""
        model_admin = django_admin.site._registry[AuditLog]

        assert model_admin.get_actions(request=None) == {}

    def test_the_model_admin_denies_all_three(self) -> None:
        """The permissions themselves, stated once. The HTTP tests above prove
        they are wired; this proves what they are."""
        model_admin = django_admin.site._registry[AuditLog]

        assert not model_admin.has_add_permission(request=None)
        assert not model_admin.has_change_permission(request=None)
        assert not model_admin.has_delete_permission(request=None)


class TestWhoCanReadIt:
    def test_an_administrator_by_role_alone_cannot(self, client, row, routed) -> None:
        """M3's distinction again. `role == ADMIN` grants the admin API; the
        admin site is a wider capability and needs `is_staff`."""
        client.force_login(_user("roleadmin@example.test", role=Role.ADMIN))

        response = client.get(f"/{routed}/core/auditlog/", follow=True)

        assert b"ACCESS_OVERRIDE_GRANTED" not in response.content

    def test_nor_a_learner(self, client, row, routed) -> None:
        client.force_login(_user("nosy@example.test"))

        response = client.get(f"/{routed}/core/auditlog/", follow=True)

        assert b"ACCESS_OVERRIDE_GRANTED" not in response.content

    def test_nor_staff_who_have_not_passed_the_second_factor(
        self, client, staff, row, routed
    ) -> None:
        """T6's control, reaching the surface T9 adds. Signed in, staff, and
        still refused until a confirmed device has been matched."""
        client.force_login(staff)

        response = client.get(f"/{routed}/core/auditlog/", follow=True)

        assert b"ACCESS_OVERRIDE_GRANTED" not in response.content
