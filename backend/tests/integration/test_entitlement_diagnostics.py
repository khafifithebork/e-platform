"""The support surface: why is this person's access wrong?

Two properties matter more than the payload shape.

The endpoint reads another person's billing history, so the negative case is
the important one — a student, an instructor and an anonymous caller must all
be refused, and being `is_staff` must not be enough.

And the trace must agree with reality. A diagnosis that described the rules in
its own words would be a second implementation of entitlement, and the first
time it disagreed it would send support looking in the wrong place — so it
reports the resolver's own decision, and a test drives a user into a state and
checks the endpoint follows.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

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
def subject(db):
    """Someone with a history worth diagnosing."""
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import fail_payment, start_subscription

    user = _user("subject@example.test")
    provider = FakeBillingProvider()
    subscription = start_subscription(user=user, provider=provider, trial_days=14)
    fail_payment(subscription=subscription, provider=provider)
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(user) -> str:
    return f"/api/v1/admin-api/users/{user.id}/diagnostics/"


class TestOnlyAdministratorsMayLook:
    def test_an_anonymous_caller_is_refused(self, client, subject) -> None:
        assert client.get(_url(subject)).status_code in (401, 403)

    def test_a_student_cannot_read_anyone_elses(self, client, subject) -> None:
        _user("nosy@example.test")
        _sign_in(client, "nosy@example.test")

        assert client.get(_url(subject)).status_code == 403

    def test_a_student_cannot_read_their_own_either(self, client, subject) -> None:
        """Not a self-service endpoint. /auth/me/ carries what a subscriber
        needs; this carries provider identifiers and another person's history,
        and widening it later is easier than narrowing it."""
        _sign_in(client, "subject@example.test")

        assert client.get(_url(subject)).status_code == 403

    def test_an_instructor_is_refused(self, client, subject) -> None:
        _user("teacher@example.test", Role.INSTRUCTOR)
        _sign_in(client, "teacher@example.test")

        assert client.get(_url(subject)).status_code == 403

    def test_being_django_staff_is_not_enough(self, client, subject) -> None:
        """M3's distinction, and the reason it exists: the day somebody is
        given staff access to fix a typo must not be the day they can read
        every subscriber's billing history."""
        _user("helper@example.test", Role.STUDENT, staff=True)
        _sign_in(client, "helper@example.test")

        assert client.get(_url(subject)).status_code == 403

    def test_an_administrator_may(self, client, subject) -> None:
        _user("admin@example.test", Role.ADMIN)
        _sign_in(client, "admin@example.test")

        assert client.get(_url(subject)).status_code == 200


class TestTheDiagnosis:
    @pytest.fixture(autouse=True)
    def _as_admin(self, client, db):
        _user("admin@example.test", Role.ADMIN)
        _sign_in(client, "admin@example.test")

    def test_it_reports_the_resolvers_own_decision(self, client, subject, settings) -> None:
        """Not a description of the rules — the answer the resolver gives. A
        trace that disagreed with what the person experiences would send
        support looking in the wrong place."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.entitlements.models import Subscription

        settings.ENTITLEMENT_GRACE_PERIOD_DAYS = 7
        Subscription.objects.filter(user=subject).update(
            current_period_end=timezone.now() - timedelta(days=8)
        )

        access = client.get(_url(subject)).json()["access"]

        assert access["allowed"] is False
        assert access["reason"] == "GRACE_PERIOD_ENDED"
        assert access["cta"] == "update_payment"

    def test_the_trace_follows_a_change_in_state(self, client, subject) -> None:
        """Provoked in both directions: a hardcoded trace would pass one of
        these two assertions and be indistinguishable from a working one."""
        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import renew

        assert client.get(_url(subject)).json()["access"]["reason"] == "GRACE_PERIOD"

        renew(
            subscription=Subscription.objects.get(user=subject),
            provider=FakeBillingProvider(),
        )

        assert client.get(_url(subject)).json()["access"]["reason"] == "SUBSCRIPTION_ACTIVE"

    def test_it_carries_the_event_log_newest_first(self, client, subject) -> None:
        """§5.2: the mutable status says what is true now; the log is the only
        thing that can say why."""
        events = client.get(_url(subject)).json()["events"]

        assert [event["event_type"] for event in events] == [
            "PAYMENT_FAILED",
            "TRIAL_STARTED",
        ]
        assert events[0]["from_status"] == "TRIALING"
        assert events[0]["to_status"] == "PAST_DUE"

    def test_it_carries_the_provider_identifier(self, client, subject) -> None:
        """The handle support needs to find the same subscription in the
        provider's dashboard. Administrators only, and it appears nowhere a
        subscriber can reach."""
        subscriptions = client.get(_url(subject)).json()["subscriptions"]

        assert subscriptions[0]["provider_subscription_id"].startswith("fake_")

    def test_it_names_who_granted_an_override_and_why(self, client, subject) -> None:
        """The entire argument for a table over a boolean on User (§5.2)."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.entitlements.models import AccessOverride

        granter = _user("granter@example.test", Role.ADMIN)
        now = timezone.now()
        AccessOverride.objects.create(
            user=subject,
            granted_by=granter,
            reason="Compensation for the outage on the 14th.",
            starts_at=now,
            ends_at=now + timedelta(days=30),
        )

        override = client.get(_url(subject)).json()["overrides"][0]

        assert override["granted_by_email"] == "granter@example.test"
        assert override["reason"] == "Compensation for the outage on the 14th."

    def test_an_unknown_user_is_a_404(self, client) -> None:
        import uuid

        response = client.get(f"/api/v1/admin-api/users/{uuid.uuid4()}/diagnostics/")

        assert response.status_code == 404

    def test_someone_with_no_history_still_diagnoses(self, client) -> None:
        """The commonest support case is "I paid and it did not work", where
        the answer is often that no subscription was ever created."""
        blank = _user("blank@example.test")

        body = client.get(_url(blank)).json()

        assert body["access"]["reason"] == "NO_SUBSCRIPTION"
        assert body["subscriptions"] == []
        assert body["events"] == []

    def test_it_does_not_fan_out_over_the_event_log(
        self, client, subject, django_assert_num_queries
    ) -> None:
        """ADR-009. A support endpoint reading a long history is exactly where
        a per-row query hides — it is fast until the account being diagnosed is
        the one with two years of events."""
        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import fail_payment, renew

        provider = FakeBillingProvider()
        for _ in range(10):
            subscription = Subscription.objects.get(user=subject)
            renew(subscription=subscription, provider=provider)
            fail_payment(subscription=subscription, provider=provider)

        # Session, user, the user being diagnosed, the resolver's override and
        # subscription checks, then the three diagnostic lists, then two more:
        # T9's administrative trail and its total. The count moved 8 -> 10 when
        # the trail arrived, and the two are separate on purpose — a LIMIT
        # cannot report what it cut off.
        with django_assert_num_queries(10):
            client.get(_url(subject))


class TestTheAdministrativeTrail:
    """T9. "What did we do to this account, and who did it" — the question
    ADR-018 §8 says `AuditLog` exists to answer, arriving on the screen support
    already opens."""

    @pytest.fixture(autouse=True)
    def _as_admin(self, client, db):
        _user("admin@example.test", Role.ADMIN)
        _sign_in(client, "admin@example.test")

    @staticmethod
    def _grant(actor, target, reason: str = "Double charged in July"):
        from apps.entitlements.services import grant_access_override

        return grant_access_override(actor=actor, user=target, days=14, reason=reason)

    def test_it_returns_what_was_done_to_this_account(self, client, subject) -> None:
        from apps.accounts.models import User

        admin = User.objects.get(email="admin@example.test")
        self._grant(admin, subject)

        trail = client.get(_url(subject)).json()["admin_trail"]

        assert trail["total"] == 1
        assert trail["entries"][0]["action"] == "ACCESS_OVERRIDE_GRANTED"
        assert trail["entries"][0]["actor_label"] == "admin@example.test"
        assert trail["entries"][0]["reason"] == "Double charged in July"

    def test_it_does_not_return_what_was_done_to_somebody_else(self, client, subject) -> None:
        """Invariant 10 on a read that crosses users by design. The endpoint is
        scoped by the id in the path, and an audit log that answered with
        everybody's history would be the widest leak in the product."""
        from apps.accounts.models import User

        admin = User.objects.get(email="admin@example.test")
        other = _user("other@example.test")
        self._grant(admin, other, reason="Nothing to do with the subject")

        trail = client.get(_url(subject)).json()["admin_trail"]

        assert trail["total"] == 0
        assert trail["entries"] == []

    def test_a_course_approval_is_not_in_it(self, client, subject) -> None:
        """User-targeted rows only, settled 2026-08-25. A course approval
        targets the course, so it belongs to that course's history. This test
        exists so the boundary is a decision on the record rather than
        something a reader has to infer from a filter."""
        from apps.accounts.models import User
        from apps.catalog.models import Course, Language
        from apps.catalog.services import approve, submit_for_review

        admin = User.objects.get(email="admin@example.test")
        subject.role = Role.INSTRUCTOR
        subject.save(update_fields=["role"])
        language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=subject
        )
        submit_for_review(course=course, by=subject)
        approve(course=course, by=admin)

        trail = client.get(_url(subject)).json()["admin_trail"]

        assert trail["total"] == 0

    def test_it_still_names_the_actor_after_their_account_is_deleted(self, client, subject) -> None:
        """Abuse case 7, through the read path rather than at the model. The
        column exists for this moment, and a serializer rendering `actor.email`
        would return null here while the row itself still knew.

        A **role change**, not an override, and the reason is worth recording:
        `AccessOverride.granted_by` is PROTECT, so an administrator who has
        ever granted an override cannot be deleted at all — the audit row's
        SET_NULL never gets a chance to matter. ADR-018 §5 argued the audit
        log must not become the reason an account cannot be removed; M4's
        override table is that reason instead, and this test would have hidden
        it behind a `ProtectedError` if it had kept using a grant.
        """
        from apps.accounts.models import User
        from apps.accounts.services import change_role

        admin = User.objects.get(email="admin@example.test")
        change_role(actor=admin, user=subject, role=Role.INSTRUCTOR, reason="Teaching now")

        # A second administrator, because deleting the one signed in would end
        # the session this test reads through.
        _user("second@example.test", Role.ADMIN)
        _sign_in(client, "second@example.test")
        User.objects.filter(pk=admin.pk).delete()

        entry = client.get(_url(subject)).json()["admin_trail"]["entries"][0]

        assert entry["actor_label"] == "admin@example.test"
        assert entry["action"] == "ROLE_CHANGED"

    def test_it_does_not_render_the_metadata_blob(self, client, subject) -> None:
        """`reason` is lifted out by name; the rest is not published. An API
        that returned the blob wholesale would publish whatever a future
        `record_admin_action(..., something=...)` put there, with no review
        against this serializer. The whole row is readable in the admin site.
        """
        from apps.accounts.models import User

        admin = User.objects.get(email="admin@example.test")
        self._grant(admin, subject)

        entry = client.get(_url(subject)).json()["admin_trail"]["entries"][0]

        assert "metadata" not in entry
        assert "override_id" not in entry

    def test_it_is_capped_but_says_how_much_it_cut(self, client, subject) -> None:
        """A list capped at fifty reporting fifty as its total would tell
        support they had seen everything, which is the one thing a truncated
        audit view must not do."""
        from apps.accounts.models import User
        from apps.entitlements.selectors import DIAGNOSTIC_TRAIL_LIMIT

        admin = User.objects.get(email="admin@example.test")
        for index in range(DIAGNOSTIC_TRAIL_LIMIT + 5):
            self._grant(admin, subject, reason=f"Grant number {index}")

        trail = client.get(_url(subject)).json()["admin_trail"]

        assert len(trail["entries"]) == DIAGNOSTIC_TRAIL_LIMIT
        assert trail["total"] == DIAGNOSTIC_TRAIL_LIMIT + 5

    def test_the_newest_entries_are_the_ones_kept(self, client, subject) -> None:
        """The twin. A cap that kept the oldest fifty would satisfy the counts
        above while hiding everything that just happened — which is precisely
        what support is looking for."""
        from apps.accounts.models import User
        from apps.entitlements.selectors import DIAGNOSTIC_TRAIL_LIMIT

        admin = User.objects.get(email="admin@example.test")
        for index in range(DIAGNOSTIC_TRAIL_LIMIT + 5):
            self._grant(admin, subject, reason=f"Grant number {index}")

        entries = client.get(_url(subject)).json()["admin_trail"]["entries"]

        assert entries[0]["reason"] == f"Grant number {DIAGNOSTIC_TRAIL_LIMIT + 4}"
