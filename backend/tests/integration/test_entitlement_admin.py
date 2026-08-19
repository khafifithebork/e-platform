"""The admin surface for entitlements.

The only way an `AccessOverride` can be created anywhere in the product, which
makes it the only way free access is granted by hand. Two properties are worth
holding: the grant is attributed to whoever made it and cannot be attributed to
anybody else, and subscription state cannot be edited into place — changing
access means granting an override, which leaves a row.

Reached through the test-only urlconf, since `admin/` stays unrouted until M10
(ADR-008 §5).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _admin_is_routed(settings):
    settings.ROOT_URLCONF = "tests.urls_with_admin"


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
    user.is_superuser = staff
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


@pytest.fixture
def admin_user(db):
    return _user("admin@example.test", Role.ADMIN, staff=True)


@pytest.fixture
def subscriber(db):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    user = _user("payer@example.test")
    start_subscription(user=user, provider=FakeBillingProvider())
    return user


class TestGrantingAnOverride:
    def test_the_grant_is_attributed_to_whoever_made_it(
        self, client, admin_user, subscriber
    ) -> None:
        """From the session, never the form. An override that can be
        attributed to somebody else defeats the reason §5.2 wants a table
        rather than a flag on User."""
        from apps.entitlements.models import AccessOverride

        _sign_in(client, "admin@example.test")
        now = timezone.now()

        client.post(
            "/admin/entitlements/accessoverride/add/",
            {
                "user": str(subscriber.pk),
                "reason": "Compensation for the outage.",
                "starts_at_0": now.date().isoformat(),
                "starts_at_1": "00:00:00",
                "ends_at_0": (now + timedelta(days=30)).date().isoformat(),
                "ends_at_1": "00:00:00",
            },
        )

        override = AccessOverride.objects.get(user=subscriber)
        assert override.granted_by == admin_user

    def test_the_grantor_cannot_be_chosen_in_the_form(self, client, admin_user, subscriber) -> None:
        """Not rendered, so there is no field to tamper with — a stronger
        guarantee than overwriting whatever was submitted."""
        _sign_in(client, "admin@example.test")

        page = client.get("/admin/entitlements/accessoverride/add/").content

        assert b'name="granted_by"' not in page

    def test_a_granted_override_takes_effect(self, client, admin_user) -> None:
        """End to end: the resolver honours what the admin granted. Without
        this the admin writes rows nothing reads."""
        from apps.catalog.models import Course, Language, Lesson, Section
        from apps.entitlements.models import AccessOverride
        from apps.entitlements.resolver import resolve_access

        student = _user("student@example.test")
        instructor = _user("teacher@example.test", Role.INSTRUCTOR)
        language = Language.objects.create(code="es", name="Spanish", native_name="Español")
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="Greetings", position=1)
        lesson = Lesson.objects.select_related("course").get(
            pk=Lesson.objects.create(
                course=course, section=section, slug="intro", title="Intro", position=1
            ).pk
        )

        assert resolve_access(user=student, lesson=lesson).reason == "NO_SUBSCRIPTION"

        now = timezone.now()
        AccessOverride.objects.create(
            user=student,
            granted_by=admin_user,
            reason="Compensation.",
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(days=30),
        )

        assert resolve_access(user=student, lesson=lesson).reason == "OVERRIDE"

    def test_a_grant_cannot_be_edited_afterwards(self, client, admin_user, subscriber) -> None:
        """An override extendable in place loses what was originally granted.
        Extending access means granting another, leaving both on the record."""
        from apps.entitlements.models import AccessOverride

        now = timezone.now()
        override = AccessOverride.objects.create(
            user=subscriber,
            granted_by=admin_user,
            reason="Original.",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        _sign_in(client, "admin@example.test")

        client.post(
            f"/admin/entitlements/accessoverride/{override.pk}/change/",
            {"reason": "Rewritten.", "ends_at_0": "2099-01-01", "ends_at_1": "00:00:00"},
        )

        override.refresh_from_db()
        assert override.reason == "Original."


class TestSubscriptionsAreNotEditable:
    def test_the_add_page_is_refused(self, client, admin_user) -> None:
        """A subscription conjured by hand has no provider behind it and no
        event explaining it."""
        _sign_in(client, "admin@example.test")

        assert client.get("/admin/entitlements/subscription/add/").status_code == 403

    def test_status_cannot_be_edited_into_place(self, client, admin_user, subscriber) -> None:
        """Editing status here would make the admin a second writer of
        subscription state beside the provider and the service layer, and
        would leave no event explaining the change."""
        from apps.entitlements.models import Subscription

        subscription = Subscription.objects.get(user=subscriber)
        _sign_in(client, "admin@example.test")

        client.post(
            f"/admin/entitlements/subscription/{subscription.pk}/change/",
            {
                "status": "ACTIVE",
                "current_period_end_0": "2099-01-01",
                "current_period_end_1": "00:00:00",
            },
        )

        subscription.refresh_from_db()
        assert subscription.current_period_end.year != 2099

    def test_a_subscription_cannot_be_deleted(self, client, admin_user, subscriber) -> None:
        """Deleting one erases the record of what somebody paid for.
        Subscriptions end by expiring, not by disappearing."""
        from apps.entitlements.models import Subscription

        subscription = Subscription.objects.get(user=subscriber)
        _sign_in(client, "admin@example.test")

        response = client.post(f"/admin/entitlements/subscription/{subscription.pk}/delete/")

        assert response.status_code == 403
        assert Subscription.objects.filter(pk=subscription.pk).exists()


class TestTheEventLogIsAppendOnly:
    def test_events_cannot_be_added_by_hand(self, client, admin_user) -> None:
        _sign_in(client, "admin@example.test")

        assert client.get("/admin/entitlements/subscriptionevent/add/").status_code == 403

    def test_events_cannot_be_deleted(self, client, admin_user, subscriber) -> None:
        """An editable audit log looks like evidence while being whatever the
        last person with access decided it should say."""
        from apps.entitlements.models import SubscriptionEvent

        event = SubscriptionEvent.objects.filter(subscription__user=subscriber).first()
        _sign_in(client, "admin@example.test")

        response = client.post(f"/admin/entitlements/subscriptionevent/{event.pk}/delete/")

        assert response.status_code == 403
        assert SubscriptionEvent.objects.filter(pk=event.pk).exists()
