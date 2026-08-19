"""Reading a lesson, end to end.

Abuse cases 1, 2 and 9 from the M4 spec. Case 9 is the one that matters most
and is easiest to fake: *the resolver is actually called*. A unit test of
`resolve_access` passes perfectly while the endpoint serving the content
forgets to consult it, which is how entitlement bypasses ship. Every assertion
here goes through HTTP and checks the response body for the paid content
itself, not for a flag claiming it was withheld.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"
BODY = "The paid content nobody unentitled may read."

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    if role != Role.STUDENT:
        user.role = role
        user.save(update_fields=["role"])
    return user


@pytest.fixture
def instructor(db):
    return _user("teacher@example.test", Role.INSTRUCTOR)


@pytest.fixture
def published_lesson(db, instructor):
    """A lesson in a course that went through review and was approved."""
    from apps.catalog.models import Course, Language, Lesson, Section
    from apps.catalog.services import approve, submit_for_review

    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    lesson = Lesson.objects.create(
        course=course, section=section, slug="intro", title="Intro", body=BODY, position=1
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return lesson


@pytest.fixture
def draft_lesson(db, instructor):
    """The same thing, never submitted."""
    from apps.catalog.models import Course, Language, Lesson, Section

    language, _ = Language.objects.get_or_create(
        code="fr", defaults={"name": "French", "native_name": "Français"}
    )
    course = Course.objects.create(
        slug="french", title="French", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Bonjour", position=1)
    return Lesson.objects.create(
        course=course, section=section, slug="bonjour", title="Bonjour", body=BODY, position=1
    )


@pytest.fixture
def subscriber(db):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    user = _user("payer@example.test")
    start_subscription(user=user, provider=FakeBillingProvider())
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


def _url(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/"


class TestTheResolverIsActuallyCalled:
    """Abuse case 9."""

    def test_a_subscriber_reads_the_body(self, client, published_lesson, subscriber) -> None:
        _sign_in(client, "payer@example.test")

        response = client.get(_url(published_lesson))

        assert response.status_code == 200
        assert response.json()["body"] == BODY

    def test_someone_without_a_subscription_never_sees_the_body(
        self, client, published_lesson
    ) -> None:
        """Abuse case 2. Asserted against the raw response bytes, not against
        a field being absent: a serializer that renamed the field, or nested
        it, would pass the weaker check while shipping the content."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        response = client.get(_url(published_lesson))

        assert response.status_code == 403
        assert BODY.encode() not in response.content

    def test_losing_the_subscription_closes_access_again(
        self, client, published_lesson, subscriber
    ) -> None:
        """Provokes the gate in both directions. A permission that always
        allowed would pass the first assertion; one that always denied would
        pass the second."""
        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        _sign_in(client, "payer@example.test")
        assert client.get(_url(published_lesson)).status_code == 200

        cancel(
            subscription=Subscription.objects.get(user=subscriber),
            provider=FakeBillingProvider(),
            immediately=True,
        )

        assert client.get(_url(published_lesson)).status_code == 403


class TestTheDenialIsActionable:
    """Abuse case 1, and ADR-004's contract."""

    def test_an_anonymous_visitor_is_told_to_sign_in(self, client, published_lesson) -> None:
        response = client.get(_url(published_lesson))

        assert response.status_code == 403
        body = response.json()
        assert body["type"] == "/problems/entitlement-denied"
        assert body["reason"] == "LOGIN_REQUIRED"
        assert body["cta"] == "login"
        assert BODY.encode() not in response.content

    def test_a_signed_in_visitor_is_told_to_subscribe(self, client, published_lesson) -> None:
        """A different answer from the anonymous one, which is the entire
        reason the decision carries a reason."""
        _user("broke@example.test")
        _sign_in(client, "broke@example.test")

        body = client.get(_url(published_lesson)).json()

        assert body["reason"] == "NO_SUBSCRIPTION"
        assert body["cta"] == "subscribe"

    def test_a_failed_card_is_distinguished_from_no_subscription(
        self, client, published_lesson, subscriber, settings
    ) -> None:
        """The case a boolean could not express: they have a subscription and
        it needs a working card, not a purchase."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.entitlements.models import Subscription
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import fail_payment

        settings.ENTITLEMENT_GRACE_PERIOD_DAYS = 7
        subscription = fail_payment(
            subscription=Subscription.objects.get(user=subscriber),
            provider=FakeBillingProvider(),
        )
        # The unpaid period ended eight days ago, so the seven-day grace is
        # over. Moved on the row rather than by freezing the clock.
        Subscription.objects.filter(pk=subscription.pk).update(
            current_period_end=timezone.now() - timedelta(days=8)
        )
        _sign_in(client, "payer@example.test")

        body = client.get(_url(published_lesson)).json()

        assert body["reason"] == "GRACE_PERIOD_ENDED"
        assert body["cta"] == "update_payment"


class TestPreviewLessons:
    def test_a_preview_is_readable_with_no_account(self, client, published_lesson) -> None:
        """The view is AllowAny so the resolver's first branch can run. A
        blanket IsAuthenticated here would refuse a preview before entitlement
        was ever consulted."""
        from apps.catalog.models import Lesson

        Lesson.objects.filter(pk=published_lesson.pk).update(is_preview=True)

        response = client.get(_url(published_lesson))

        assert response.status_code == 200
        assert response.json()["body"] == BODY


class TestVisibilityIsNotEntitlement:
    """The gate the resolver cannot provide.

    `resolve_access` knows about subscriptions, not publication. A paying
    subscriber passes its SUBSCRIPTION_ACTIVE branch on a draft lesson, so
    without a visibility filter the endpoint serves unpublished content to
    anyone who has paid.
    """

    def test_a_subscriber_cannot_read_an_unpublished_lesson(
        self, client, draft_lesson, subscriber
    ) -> None:
        _sign_in(client, "payer@example.test")

        response = client.get(_url(draft_lesson))

        # 404, not 403: a 403 would confirm the draft exists (§6.3).
        assert response.status_code == 404
        assert BODY.encode() not in response.content

    def test_the_instructor_can_read_their_own_draft(
        self, client, draft_lesson, instructor
    ) -> None:
        """Writing a course means reading it back."""
        _sign_in(client, "teacher@example.test")

        response = client.get(_url(draft_lesson))

        assert response.status_code == 200
        assert response.json()["body"] == BODY

    def test_another_instructor_cannot(self, client, draft_lesson) -> None:
        _user("rival@example.test", Role.INSTRUCTOR)
        _sign_in(client, "rival@example.test")

        assert client.get(_url(draft_lesson)).status_code == 404

    def test_an_admin_can(self, client, draft_lesson) -> None:
        _user("boss@example.test", Role.ADMIN)
        _sign_in(client, "boss@example.test")

        assert client.get(_url(draft_lesson)).status_code == 200


class TestThereIsNoListRoute:
    def test_listing_every_lesson_is_not_offered(self, client, published_lesson) -> None:
        """This failed when written, and the failure was the point.

        The view was a ReadOnlyModelViewSet, which provides `list` as well as
        `retrieve`. Object-level permissions are not consulted for a list, so
        `GET /lessons/` answered 200 with every visible lesson body to an
        anonymous caller — a complete entitlement bypass behind a class whose
        docstring said "retrieve only".
        """
        assert client.get("/api/v1/lessons/").status_code == 404

    def test_no_route_serves_a_body_to_an_anonymous_caller(self, client, published_lesson) -> None:
        """The general form of the bug above: whatever routes exist under
        /lessons/, none of them may hand the content to someone anonymous."""
        for path in ("/api/v1/lessons/", f"/api/v1/lessons/{published_lesson.id}/"):
            assert BODY.encode() not in client.get(path).content, path


class TestQueryCost:
    def test_reading_a_lesson_costs_a_fixed_number_of_queries(
        self, client, published_lesson, subscriber, django_assert_num_queries
    ) -> None:
        """ADR-009. This is the hottest authenticated path in the product."""
        _sign_in(client, "payer@example.test")

        # Session, user, the lesson with its course, the override check, the
        # subscription fetch.
        with django_assert_num_queries(5):
            client.get(_url(published_lesson))
