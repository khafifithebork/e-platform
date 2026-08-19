"""The current-user endpoint.

Closes the last two abuse cases in the M2 threat model:

7. An unverified account can sign in (ADR-005 §2.3), so this endpoint must
   report that state rather than pretend it cannot happen — the frontend needs
   it to prompt.
8. Whose data is returned is derived from the session and nothing else. There
   is no identifier to manipulate, which is the strongest form of "you cannot
   read someone else's profile".

`architecture.md` §6.2 shows an `access` object here. It is deliberately absent
until M4 builds the entitlement resolver: adding an optional object later is a
backward-compatible change, whereas shipping a fake one now would invite the
frontend to depend on a shape that has no logic behind it.
"""

from __future__ import annotations

import pytest

ME = "/api/v1/auth/me/"
LOGIN = "/api/v1/auth/login/"
PASSWORD = "a-sufficiently-long-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def account(db):
    from apps.accounts.services import create_account

    return create_account(email="learner@example.test", password=PASSWORD)


def _sign_in(client, account):
    client.post(
        LOGIN, {"email": account.email, "password": PASSWORD}, content_type="application/json"
    )


@pytest.mark.django_db
class TestRequiresAuthentication:
    def test_anonymous_is_refused(self, client) -> None:
        response = client.get(ME)

        assert response.status_code in (401, 403)

    def test_the_refusal_is_a_problem_document(self, client) -> None:
        """One error shape everywhere (M1 T3)."""
        response = client.get(ME)

        assert response["Content-Type"] == "application/problem+json"

    def test_after_logout_it_is_refused_again(self, client, account) -> None:
        _sign_in(client, account)
        client.post("/api/v1/auth/logout/", content_type="application/json")

        assert client.get(ME).status_code in (401, 403)


@pytest.mark.django_db
class TestReturnsTheSignedInUser:
    def test_returns_the_caller(self, client, account) -> None:
        _sign_in(client, account)

        body = client.get(ME).json()

        assert body["email"] == account.email
        assert body["id"] == str(account.id)
        assert body["role"] == "STUDENT"

    def test_reports_verification_state(self, client, account) -> None:
        """Abuse case 7. An unverified user can sign in, so the frontend needs
        to know in order to prompt — and M9 gates trial start on it."""
        _sign_in(client, account)

        assert client.get(ME).json()["is_email_verified"] is False

    def test_includes_the_profile(self, client, account) -> None:
        _sign_in(client, account)

        assert "profile" in client.get(ME).json()

    def test_includes_the_entitlement_decision(self, client, account) -> None:
        """Replaces a guard that asserted this was *absent* until M4, written
        to fail exactly once so nobody shipped a placeholder the frontend could
        depend on. M4 arrived and it fired, which is what it was for.

        architecture.md §6.2: /auth/me/ returns the decision "so the frontend
        never re-derives access rules".
        """
        _sign_in(client, account)

        access = client.get(ME).json()["access"]

        assert access["allowed"] is False
        assert access["reason"] == "NO_SUBSCRIPTION"
        assert access["cta"] == "subscribe"

    def test_the_decision_follows_the_subscription(self, client, account) -> None:
        """Provoked in both directions. A hardcoded denial would pass the test
        above and be indistinguishable from a working resolver."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        start_subscription(user=account, provider=FakeBillingProvider())
        _sign_in(client, account)

        access = client.get(ME).json()["access"]

        assert access["allowed"] is True
        assert access["reason"] == "SUBSCRIPTION_ACTIVE"
        assert access["cta"] is None


@pytest.mark.django_db
class TestLeaksNothing:
    def test_no_password_material_is_returned(self, client, account) -> None:
        _sign_in(client, account)
        body = client.get(ME).content.decode()

        assert "password" not in body.lower()
        assert "argon2" not in body.lower()

    def test_no_permission_or_staff_flags(self, client, account) -> None:
        """Internal authorisation detail. The frontend branches on `role`."""
        _sign_in(client, account)
        body = client.get(ME).json()

        for field in ("is_staff", "is_superuser", "user_permissions", "groups"):
            assert field not in body


@pytest.mark.django_db
class TestIdentityComesOnlyFromTheSession:
    """Abuse case 8."""

    def test_a_query_parameter_cannot_select_another_user(self, client, account) -> None:
        from apps.accounts.services import create_account

        other = create_account(email="someone.else@example.test", password=PASSWORD)
        _sign_in(client, account)

        for attempt in (f"?id={other.id}", f"?user={other.id}", f"?email={other.email}"):
            body = client.get(f"{ME}{attempt}").json()

            assert body["email"] == account.email

    def test_a_header_cannot_select_another_user(self, client, account) -> None:
        from apps.accounts.services import create_account

        other = create_account(email="someone.else@example.test", password=PASSWORD)
        _sign_in(client, account)

        body = client.get(ME, headers={"x-user-id": str(other.id)}).json()

        assert body["email"] == account.email


@pytest.mark.django_db
class TestQueryCount:
    def test_does_not_fan_out(self, client, account, django_assert_num_queries) -> None:
        """The most-called authenticated endpoint in the product: the frontend
        hits it on load and after every auth transition.

        Five queries:

        1. the session,
        2. the user, loaded by Django's authentication middleware,
        3. the user again with the profile joined,
        4. the access-override check,
        5. the subscriptions.

        Four and five are the entitlement decision, added in M4. They are the
        cost of the frontend not re-deriving access rules, and they are the
        first thing M8's cache will remove.

        The third looks wasteful and is not avoidable by dropping the selector:
        reading ``request.user.student_profile`` lazily costs exactly the same
        extra query. The selector earns its place on layering (invariant 2) and
        because the join stays one query as more relations are added — not on
        saving one today.

        The number is pinned so that a sixth query has to be argued for.
        """
        _sign_in(client, account)

        with django_assert_num_queries(5):
            client.get(ME)
