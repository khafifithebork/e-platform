"""Reading a lesson by course slug and lesson slug. M16 T3.

`architecture.md` §6.2 specified `GET courses/{slug}/lessons/{lesson_slug}/` at
M0 and it was never built — M7 shipped `/lessons/{id}/` instead. **The schema
has been shaped for this route the whole time**: ADR-007 §1 put a redundant
`course` foreign key on `Lesson` for exactly this, backed by
`lesson_slug_unique_per_course`, and until now that constraint guarded a URL
nothing served.

**This is a second way to reach paid content, so the negatives are the point.**
`test_gated_lesson.py` proves the gates on `/lessons/{id}/`. Everything here
exists to prove the same gates apply on the new path — because the failure to
design against is not a broken route, it is a working one that skips a check
the old route makes.

The subtle one is `test_the_object_permission_actually_runs`. Overriding
`get_object` skips the base implementation that calls
`check_object_permissions`, so the entitlement gate has to be invoked by hand —
and forgetting that line yields a route that serves every lesson body to
anybody who can guess a slug, while every other test here still passes.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.catalog.models import Course, Language, Lesson, Section
from apps.catalog.services import approve, submit_for_review

pytestmark = pytest.mark.django_db

PASSWORD = "a-long-enough-passphrase"
BODY = "Hola. This is the lesson body, and it is paid content."


def _user(email: str, role: str = Role.STUDENT):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _sign_in(client, email: str) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def published_course(db):
    instructor = _user("teacher@example.test", Role.INSTRUCTOR)
    admin = _user("approver@example.test", Role.ADMIN)
    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    Lesson.objects.create(
        course=course,
        section=section,
        slug="intro",
        title="Intro",
        body=BODY,
        position=1,
        is_preview=True,
    )
    Lesson.objects.create(
        course=course,
        section=section,
        slug="paid",
        title="Paid",
        body=BODY,
        position=2,
        is_preview=False,
    )
    submit_for_review(course=course, by=instructor)
    approve(course=course, by=admin)
    return course


@pytest.fixture
def draft_course(db):
    instructor = _user("teacher2@example.test", Role.INSTRUCTOR)
    language, _ = Language.objects.get_or_create(
        code="fr", defaults={"name": "French", "native_name": "Français"}
    )
    course = Course.objects.create(
        slug="french", title="French", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Bonjour", position=1)
    Lesson.objects.create(
        course=course,
        section=section,
        slug="secret",
        title="Secret",
        body=BODY,
        position=1,
        is_preview=True,
    )
    return course


def _url(course_slug: str, lesson_slug: str) -> str:
    return f"/api/v1/courses/{course_slug}/lessons/{lesson_slug}/"


class TestTheRouteExists:
    def test_a_preview_lesson_is_readable_by_anyone(self, client, published_course) -> None:
        """The resolver allows a preview before it asks who is calling, and
        `AllowAny` is what lets that branch run. A blanket `IsAuthenticated`
        here would refuse an anonymous visitor before the resolver spoke."""
        response = client.get(_url("spanish", "intro"))

        assert response.status_code == 200

    def test_and_returns_the_body(self, client, published_course) -> None:
        """The twin. A 200 with an empty body would satisfy the test above and
        serve nothing."""
        response = client.get(_url("spanish", "intro"))

        assert BODY in response.json()["body"]

    def test_it_is_the_same_lesson_the_id_route_serves(self, client, published_course) -> None:
        """One resource, two addresses. If these diverged, one of them would be
        reading through a different queryset — which is where a second access
        rule grows."""
        lesson = Lesson.objects.get(course=published_course, slug="intro")

        by_slug = client.get(_url("spanish", "intro")).json()
        by_id = client.get(f"/api/v1/lessons/{lesson.pk}/").json()

        assert by_slug == by_id


class TestTheEntitlementGateApplies:
    def test_a_paid_lesson_refuses_an_anonymous_visitor(self, client, published_course) -> None:
        response = client.get(_url("spanish", "paid"))

        assert response.status_code == 403

    def test_the_refusal_carries_a_reason(self, client, published_course) -> None:
        """ADR-004. The interface branches on this, and M16 T4 renders six
        different messages from it — a bare 403 would collapse them into one."""
        response = client.get(_url("spanish", "paid"))

        assert response.json()["reason"] == "LOGIN_REQUIRED"

    def test_a_signed_in_learner_without_a_subscription_is_refused(
        self, client, published_course
    ) -> None:
        _user("learner@example.test")
        _sign_in(client, "learner@example.test")

        response = client.get(_url("spanish", "paid"))

        assert response.status_code == 403
        assert response.json()["reason"] == "NO_SUBSCRIPTION"

    def test_the_body_is_absent_from_a_refusal(self, client, published_course) -> None:
        """The property that matters more than the status code. A 403 whose
        payload still carried the lesson would be a paywall in name only."""
        response = client.get(_url("spanish", "paid"))

        assert BODY not in response.content.decode()

    def test_the_object_permission_actually_runs(self, client, published_course) -> None:
        """**The specific hazard of overriding `get_object`.**

        DRF's base `get_object` calls `check_object_permissions`. Overriding it
        for a two-field lookup skips that, so the call has to be made by hand —
        and forgetting it produces a route that serves every lesson body to
        anybody who can guess a slug, while every other test in this file still
        passes.

        Asserted by removing the only thing that can refuse: with an entitled
        user the same URL returns 200, so a 403 here is the permission class
        running rather than something else failing.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.entitlements.models import Subscription, SubscriptionStatus

        refused = client.get(_url("spanish", "paid"))

        subscriber = _user("subscriber@example.test")
        Subscription.objects.create(
            user=subscriber,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=timezone.now() + timedelta(days=30),
            provider="fake",
        )
        _sign_in(client, "subscriber@example.test")
        allowed = client.get(_url("spanish", "paid"))

        assert refused.status_code == 403
        assert allowed.status_code == 200


class TestThePublicationGateApplies:
    def test_a_lesson_in_an_unpublished_course_is_404(self, client, draft_course) -> None:
        """404, not 403 — §6.3. A 403 confirms the lesson exists, which tells
        somebody probing for unreleased courses exactly what they wanted."""
        response = client.get(_url("french", "secret"))

        assert response.status_code == 404

    def test_even_though_it_is_marked_preview(self, client, draft_course) -> None:
        """The twin, and the reason both gates exist. The resolver would allow
        a preview; the queryset is what stops an unpublished one being reached
        at all. Without the publication gate, `is_preview` on a draft lesson
        publishes it."""
        lesson = Lesson.objects.get(course=draft_course, slug="secret")

        assert lesson.is_preview is True

    def test_the_body_does_not_leak_in_the_404(self, client, draft_course) -> None:
        response = client.get(_url("french", "secret"))

        assert BODY not in response.content.decode()


class TestTheTwoSlugsMustAgree:
    def test_a_real_lesson_under_the_wrong_course_is_404(
        self, client, published_course, draft_course
    ) -> None:
        """The lookup is on both slugs, not on the lesson slug alone. Matching
        only the lesson would make the course segment decoration — and a
        decorative path segment is one somebody eventually removes."""
        response = client.get(_url("french", "intro"))

        assert response.status_code == 404

    def test_an_unknown_lesson_slug_is_404(self, client, published_course) -> None:
        response = client.get(_url("spanish", "no-such-lesson"))

        assert response.status_code == 404

    def test_an_unknown_course_slug_is_404(self, client, published_course) -> None:
        response = client.get(_url("no-such-course", "intro"))

        assert response.status_code == 404


class TestTheConstraintThisRouteDependsOn:
    def test_a_lesson_slug_is_unique_within_its_course(self) -> None:
        """`lesson_slug_unique_per_course`, and this route is what it was for.

        ADR-007 §1 put a redundant `course` foreign key on `Lesson` to make
        this expressible, on the grounds that "uniqueness enforced in a service
        is uniqueness a bulk import walks straight past". Without the
        constraint this lookup returns an arbitrary row among duplicates — a
        route that serves a different lesson depending on insertion order.
        """
        constraints = {constraint.name for constraint in Lesson._meta.constraints}

        assert "lesson_slug_unique_per_course" in constraints
