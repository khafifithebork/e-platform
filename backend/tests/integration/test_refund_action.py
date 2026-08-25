"""The refund route: who may call it, what it validates, and what it admits.

architecture.md §6.10 names `POST subscriptions/{id}/refund/`. M10 ships the
half of it that is ours — the permission boundary, the validation and an honest
refusal — and not the half that belongs to a payment provider nobody has
chosen yet (§11 #1, ADR-018 §3).

The refusal answers **501**, not 503. 503 tells a client to try again shortly,
which is false: nothing about waiting will make this work. 501 says this server
does not do this, which is exactly true until M8.

`TestTheRefusalIsNotAnExcuse` is the group worth reading. A route that answered
501 to everything would pass a careless reading of this file, so each check
above the refusal is proven to fire *before* it.
"""

from __future__ import annotations

import uuid
from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import Role
from apps.core.models import AuditLog
from apps.entitlements.models import Subscription, SubscriptionEvent

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


def _user(email: str, role: str = Role.STUDENT, *, staff: bool = False):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.is_staff = staff
    user.save(update_fields=["role", "is_staff"])
    return user


@pytest.fixture
def admin(db):
    return _user("admin@example.test", Role.ADMIN)


@pytest.fixture
def learner(db):
    return _user("learner@example.test")


@pytest.fixture
def subscription(db, learner) -> Subscription:
    call_command("billing", "start", email=learner.email, stdout=StringIO())
    return Subscription.objects.get(user=learner)


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(subscription_id) -> str:
    return f"/api/v1/admin-api/subscriptions/{subscription_id}/refund/"


def _refund(client, subscription_id, *, reason: str = "Double charged in July"):
    return client.post(_url(subscription_id), {"reason": reason}, content_type="application/json")


class TestOnlyAdministrators:
    def test_a_learner_cannot_refund_their_own_subscription(
        self, client, learner, subscription
    ) -> None:
        _sign_in(client, "learner@example.test")

        assert _refund(client, subscription.id).status_code == 403

    def test_nor_can_an_instructor(self, client, subscription) -> None:
        _user("teacher@example.test", Role.INSTRUCTOR)
        _sign_in(client, "teacher@example.test")

        assert _refund(client, subscription.id).status_code == 403

    def test_nor_can_a_staff_account_that_is_not_an_administrator(
        self, client, subscription
    ) -> None:
        """M3's distinction, and the reason it exists. `is_staff` is the flag
        that opens the Django admin site; the day somebody is given it to fix a
        typo must not be the day they can move money."""
        _user("staffer@example.test", Role.STUDENT, staff=True)
        _sign_in(client, "staffer@example.test")

        assert _refund(client, subscription.id).status_code == 403

    def test_nor_anonymous(self, client, subscription) -> None:
        assert _refund(client, subscription.id).status_code in (401, 403)

    def test_a_refusal_writes_no_audit_row(self, client, learner, subscription) -> None:
        """A refused attempt is not an administrative action."""
        _sign_in(client, "learner@example.test")

        _refund(client, subscription.id)

        assert not AuditLog.objects.exists()

    def test_and_permission_is_decided_before_the_subscription_is_looked_up(
        self, client, learner
    ) -> None:
        """A 404 here would tell a learner which subscription ids exist. The
        boundary answers first, so it answers the same for every id."""
        _sign_in(client, "learner@example.test")

        assert _refund(client, uuid.uuid4()).status_code == 403


class TestTheGapIsVisible:
    def test_an_administrator_is_told_it_is_not_implemented(
        self, client, admin, subscription
    ) -> None:
        _sign_in(client, "admin@example.test")

        assert _refund(client, subscription.id).status_code == 501

    def test_the_body_is_a_problem_document_with_its_own_type(
        self, client, admin, subscription
    ) -> None:
        """ADR-004: clients branch on the type, not the status. A 501 with
        `about:blank` would be indistinguishable from any other unimplemented
        thing the server might grow."""
        _sign_in(client, "admin@example.test")

        response = _refund(client, subscription.id)

        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["type"] == "/problems/refund-not-available"
        assert response.json()["status"] == 501

    def test_no_audit_row_is_written(self, client, admin, subscription) -> None:
        """T8's settled decision, asserted at the surface as well as the
        service. Nothing happened, so nothing is recorded."""
        _sign_in(client, "admin@example.test")

        _refund(client, subscription.id)

        assert not AuditLog.objects.exists()

    def test_the_subscription_is_untouched(self, client, admin, subscription) -> None:
        before = (subscription.status, subscription.current_period_end)
        events = SubscriptionEvent.objects.filter(subscription=subscription).count()

        _sign_in(client, "admin@example.test")
        _refund(client, subscription.id)

        subscription.refresh_from_db()
        assert (subscription.status, subscription.current_period_end) == before
        assert SubscriptionEvent.objects.filter(subscription=subscription).count() == events


class TestTheRefusalIsNotAnExcuse:
    """Everything checked above the refusal is inherited by M8. Everything
    checked below it would have to be written next to a live payments call."""

    def test_a_blank_reason_is_a_400_not_a_501(self, client, admin, subscription) -> None:
        _sign_in(client, "admin@example.test")

        assert _refund(client, subscription.id, reason="   ").status_code == 400

    def test_a_missing_reason_is_a_400_not_a_501(self, client, admin, subscription) -> None:
        _sign_in(client, "admin@example.test")

        response = client.post(_url(subscription.id), {}, content_type="application/json")

        assert response.status_code == 400

    def test_an_unknown_subscription_is_a_404_not_a_501(self, client, admin) -> None:
        """The route resolves an object. A blanket 501 would hide the day that
        stopped working."""
        _sign_in(client, "admin@example.test")

        assert _refund(client, uuid.uuid4()).status_code == 404

    def test_a_bad_body_is_answered_before_the_id_is_looked_up(self, client, admin) -> None:
        """Pinned rather than asserted in a comment. A malformed request gets
        the same answer whether or not the subscription exists."""
        _sign_in(client, "admin@example.test")

        response = client.post(_url(uuid.uuid4()), {}, content_type="application/json")

        assert response.status_code == 400

    def test_the_route_rejects_a_get(self, client, admin, subscription) -> None:
        """There is nothing to read here. A refund is an act, and a surface
        that answered GET would invite a link to it."""
        _sign_in(client, "admin@example.test")

        assert client.get(_url(subscription.id)).status_code == 405
