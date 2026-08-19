"""Every branch of the entitlement resolver, and every boundary.

CLAUDE.md §8 requires 100% branch coverage here, and §4.5 rule 4 names the
boundaries specifically: "period end exactly now, grace period boundary, trial
end at midnight". Those are tested at the second, from both sides, because an
off-by-one in this function either gives the product away or locks out someone
who has paid.

Subscriptions are put into each state through the real services and the real
fake provider rather than by writing `status` directly. A row assembled by
hand can be in a state production cannot reach, and a test of an impossible
state proves nothing about a real one.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


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
def lesson(db, instructor):
    """A gated lesson, fetched the way callers are told to fetch it."""
    from apps.catalog.models import Course, Language, Lesson, Section

    language = Language.objects.create(code="es", name="Spanish", native_name="Español")
    course = Course.objects.create(
        slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
    )
    section = Section.objects.create(course=course, title="Greetings", position=1)
    Lesson.objects.create(course=course, section=section, slug="intro", title="Intro", position=1)
    return Lesson.objects.select_related("course").get(slug="intro")


@pytest.fixture
def preview_lesson(db, lesson):
    from apps.catalog.models import Lesson

    Lesson.objects.filter(pk=lesson.pk).update(is_preview=True)
    return Lesson.objects.select_related("course").get(pk=lesson.pk)


@pytest.fixture
def student(db):
    return _user("student@example.test")


def _resolve(user, lesson):
    from apps.entitlements.resolver import resolve_access

    return resolve_access(user=user, lesson=lesson)


def _start(user, *, trial_days=None):
    from apps.entitlements.providers.fake import FakeBillingProvider
    from apps.entitlements.services import start_subscription

    return start_subscription(user=user, provider=FakeBillingProvider(), trial_days=trial_days)


def _set_period_end(subscription, when):
    """Move the clock forward by moving the row, not by freezing time.

    Freezing time would need a dependency; moving the boundary tests exactly
    the same comparison from the other side.
    """
    from apps.entitlements.models import Subscription

    Subscription.objects.filter(pk=subscription.pk).update(current_period_end=when)
    return Subscription.objects.get(pk=subscription.pk)


class TestPreview:
    def test_a_preview_lesson_is_open_to_anonymous_visitors(self, preview_lesson) -> None:
        """First branch, before authentication: the marketing pages depend on
        this working for people with no account."""
        from django.contrib.auth.models import AnonymousUser

        decision = _resolve(AnonymousUser(), preview_lesson)

        assert decision.allowed
        assert decision.reason == "PREVIEW"

    def test_a_preview_lesson_is_open_to_someone_with_an_expired_subscription(
        self, preview_lesson, student
    ) -> None:
        subscription = _start(student)
        _set_period_end(subscription, timezone.now() - timedelta(days=400))

        assert _resolve(student, preview_lesson).allowed


class TestAnonymous:
    def test_a_gated_lesson_asks_an_anonymous_visitor_to_sign_in(self, lesson) -> None:
        from django.contrib.auth.models import AnonymousUser

        decision = _resolve(AnonymousUser(), lesson)

        assert not decision.allowed
        assert decision.reason == "LOGIN_REQUIRED"
        # Not "subscribe": they may already have paid and simply not be signed
        # in, and being asked to buy something you own is its own bug report.
        assert decision.cta == "login"

    def test_none_is_treated_as_anonymous(self, lesson) -> None:
        """Callers outside a request — the worker, a management command — have
        no AnonymousUser to hand."""
        assert _resolve(None, lesson).reason == "LOGIN_REQUIRED"


class TestStaffAndOwners:
    def test_an_admin_sees_everything(self, lesson) -> None:
        admin = _user("admin@example.test", Role.ADMIN)

        assert _resolve(admin, lesson).reason == "STAFF"

    def test_the_courses_instructor_sees_their_own_lesson(self, lesson, instructor) -> None:
        """An instructor locked out of the course they are writing cannot
        check their own work."""
        assert _resolve(instructor, lesson).reason == "COURSE_OWNER"

    def test_another_instructor_is_not_privileged(self, lesson) -> None:
        """Being an instructor grants nothing on somebody else's course."""
        other = _user("other@example.test", Role.INSTRUCTOR)

        decision = _resolve(other, lesson)

        assert not decision.allowed
        assert decision.reason == "NO_SUBSCRIPTION"


class TestOverrides:
    def _grant(self, user, granted_by, *, starts_at, ends_at):
        from apps.entitlements.models import AccessOverride

        return AccessOverride.objects.create(
            user=user,
            granted_by=granted_by,
            reason="Support goodwill.",
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def test_a_current_override_grants_access_without_a_subscription(self, lesson, student) -> None:
        admin = _user("admin@example.test", Role.ADMIN)
        now = timezone.now()
        self._grant(
            student, admin, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1)
        )

        assert _resolve(student, lesson).reason == "OVERRIDE"

    def test_an_override_that_ended_yesterday_grants_nothing(self, lesson, student) -> None:
        admin = _user("admin@example.test", Role.ADMIN)
        now = timezone.now()
        self._grant(
            student, admin, starts_at=now - timedelta(days=8), ends_at=now - timedelta(days=1)
        )

        assert not _resolve(student, lesson).allowed

    def test_an_override_starting_tomorrow_grants_nothing_yet(self, lesson, student) -> None:
        """Filtering on only one bound is how a week's grant becomes a year's."""
        admin = _user("admin@example.test", Role.ADMIN)
        now = timezone.now()
        self._grant(
            student, admin, starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=8)
        )

        assert not _resolve(student, lesson).allowed


class TestSubscriptionStates:
    def test_no_subscription_at_all(self, lesson, student) -> None:
        decision = _resolve(student, lesson)

        assert decision.reason == "NO_SUBSCRIPTION"
        assert decision.cta == "subscribe"

    def test_an_active_subscription_grants_access(self, lesson, student) -> None:
        _start(student)

        assert _resolve(student, lesson).reason == "SUBSCRIPTION_ACTIVE"

    def test_a_trial_in_progress_grants_access(self, lesson, student) -> None:
        _start(student, trial_days=14)

        assert _resolve(student, lesson).reason == "TRIAL"

    def test_an_expired_subscription_is_distinguished_from_never_having_one(
        self, lesson, student
    ) -> None:
        """Different messages. "Your subscription ended" and "you never had
        one" call for different things from the person reading them."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        subscription = _start(student)
        cancel(subscription=subscription, provider=FakeBillingProvider(), immediately=True)

        assert _resolve(student, lesson).reason == "SUBSCRIPTION_EXPIRED"


class TestBoundaries:
    """§4.5 rule 4. Each tested from both sides, at the second."""

    def test_a_trial_that_ends_exactly_now_is_over(self, lesson, student) -> None:
        from apps.entitlements.models import Subscription

        subscription = _start(student, trial_days=14)
        Subscription.objects.filter(pk=subscription.pk).update(trial_end=timezone.now())

        assert _resolve(student, lesson).reason == "TRIAL_EXPIRED"

    def test_a_trial_with_a_second_left_still_grants_access(self, lesson, student) -> None:
        from apps.entitlements.models import Subscription

        subscription = _start(student, trial_days=14)
        Subscription.objects.filter(pk=subscription.pk).update(
            trial_end=timezone.now() + timedelta(seconds=1)
        )

        assert _resolve(student, lesson).reason == "TRIAL"

    def test_a_cancelled_subscription_grants_access_until_the_period_ends(
        self, lesson, student
    ) -> None:
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        subscription = _start(student)
        cancel(subscription=subscription, provider=FakeBillingProvider())

        assert _resolve(student, lesson).reason == "CANCELED_BUT_PAID"

    def test_a_cancelled_subscription_one_second_past_the_period_is_denied(
        self, lesson, student
    ) -> None:
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        subscription = _start(student)
        subscription = cancel(subscription=subscription, provider=FakeBillingProvider())
        _set_period_end(subscription, timezone.now() - timedelta(seconds=1))

        assert _resolve(student, lesson).reason == "SUBSCRIPTION_EXPIRED"

    def test_past_due_inside_the_grace_period_still_grants_access(
        self, lesson, student, settings
    ) -> None:
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import fail_payment

        settings.ENTITLEMENT_GRACE_PERIOD_DAYS = 7
        subscription = _start(student)
        subscription = fail_payment(subscription=subscription, provider=FakeBillingProvider())
        # The period ended six days ago: one day of grace left.
        _set_period_end(subscription, timezone.now() - timedelta(days=6))

        assert _resolve(student, lesson).reason == "GRACE_PERIOD"

    def test_past_due_one_second_past_the_grace_period_is_denied(
        self, lesson, student, settings
    ) -> None:
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import fail_payment

        settings.ENTITLEMENT_GRACE_PERIOD_DAYS = 7
        subscription = _start(student)
        subscription = fail_payment(subscription=subscription, provider=FakeBillingProvider())
        _set_period_end(subscription, timezone.now() - timedelta(days=7, seconds=1))

        decision = _resolve(student, lesson)

        assert decision.reason == "GRACE_PERIOD_ENDED"
        # Not "subscribe" — they have a subscription, it needs a working card.
        assert decision.cta == "update_payment"

    def test_the_grace_period_honours_the_setting(self, lesson, student, settings) -> None:
        """The boundary is a configured value, so the configuration is what
        the test moves. A literal 7 in the resolver would pass this by
        coincidence at the default and fail here."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import fail_payment

        settings.ENTITLEMENT_GRACE_PERIOD_DAYS = 30
        subscription = _start(student)
        subscription = fail_payment(subscription=subscription, provider=FakeBillingProvider())
        _set_period_end(subscription, timezone.now() - timedelta(days=20))

        assert _resolve(student, lesson).reason == "GRACE_PERIOD"


class TestSeveralSubscriptions:
    """The case the model's constraint deliberately allows."""

    def test_a_fresh_subscription_beside_a_cancelled_one_grants_access(
        self, lesson, student
    ) -> None:
        """Resubscribing before the old period ends must not deny access.
        Fetching "the" subscription and reasoning about it would answer
        correctly for most users and lock out the ones who just paid."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        first = _start(student)
        cancel(subscription=first, provider=FakeBillingProvider())
        _start(student)  # allowed: CANCELED is not a live status

        assert _resolve(student, lesson).reason == "SUBSCRIPTION_ACTIVE"

    def test_the_most_informative_denial_wins(self, lesson, student) -> None:
        """Somebody holding an ended subscription should be told it ended, not
        that they never had one."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        first = _start(student)
        cancel(subscription=first, provider=FakeBillingProvider(), immediately=True)
        second = _start(student)
        cancel(subscription=second, provider=FakeBillingProvider(), immediately=True)

        assert _resolve(student, lesson).reason == "SUBSCRIPTION_EXPIRED"


class TestTheDecisionItself:
    def test_a_decision_cannot_be_edited_after_the_fact(self, lesson, student) -> None:
        """Frozen, so a caller cannot talk itself out of a refusal."""
        import dataclasses

        decision = _resolve(student, lesson)

        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.allowed = True

    def test_truthiness_follows_allowed(self, lesson, student, preview_lesson) -> None:
        """Without __bool__, `if decision:` is always true and every caller
        that writes it grants access unconditionally."""
        assert not _resolve(student, lesson)
        assert _resolve(student, preview_lesson)

    def test_every_denial_carries_a_call_to_action(self, lesson, student) -> None:
        assert _resolve(student, lesson).cta is not None

    def test_the_trial_scope_seam_is_one_function(self) -> None:
        """The trial scoping rule is undecided (spec §3.2). It must stay
        isolated in `trial_covers`, so that deciding it changes one function —
        this fails if the trial branch grows a second decision point."""
        import inspect

        from apps.entitlements import resolver

        source = inspect.getsource(resolver._decide_for)
        trial_branch = source.split("TRIALING")[1]

        assert trial_branch.count("trial_covers") == 1


class TestQueryCost:
    """ADR-009. This runs on every request for gated content."""

    def test_resolving_costs_a_fixed_number_of_queries(
        self, lesson, student, django_assert_num_queries
    ) -> None:
        """Two: the override check and the subscription fetch. The lesson's
        course is already selected by the caller, which is what the resolver's
        docstring asks for — without that this is three."""
        _start(student)

        with django_assert_num_queries(2):
            _resolve(student, lesson)

    def test_the_cost_does_not_grow_with_the_number_of_subscriptions(
        self, lesson, student, django_assert_num_queries
    ) -> None:
        """The count is what matters, not the number. A per-subscription query
        would still pass the test above, which has one subscription."""
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import cancel

        for _ in range(5):
            subscription = _start(student)
            cancel(subscription=subscription, provider=FakeBillingProvider(), immediately=True)
        _start(student)

        with django_assert_num_queries(2):
            _resolve(student, lesson)

    def test_a_preview_lesson_costs_nothing(self, preview_lesson, student) -> None:
        """The first branch returns before touching the database. Preview
        lessons are on public pages and must not put a query on each one."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            _resolve(student, preview_lesson)

        assert len(captured) == 0


class TestTheTrialScopeBranch:
    """The branch spec §3.2 will turn on.

    Unreachable while `trial_covers` grants everything, so it is reached by
    substituting a scoping rule that refuses. That is not mocking our own
    service layer to assert it was called (CLAUDE.md §6) — the resolver runs
    for real and the assertion is on the decision it returns. Without this the
    branch ships untested and 100% coverage (§8) is not met.
    """

    def test_a_trial_that_does_not_cover_the_lesson_is_denied(
        self, lesson, student, monkeypatch
    ) -> None:
        from apps.entitlements import resolver

        _start(student, trial_days=14)
        monkeypatch.setattr(resolver, "trial_covers", lambda **_: False)

        decision = _resolve(student, lesson)

        assert not decision.allowed
        assert decision.reason == "TRIAL_SCOPE"
        assert decision.cta == "subscribe"

    def test_an_expired_trial_is_reported_as_expired_not_out_of_scope(
        self, lesson, student, monkeypatch
    ) -> None:
        """Order matters: someone whose trial ran out should be told that,
        even if the lesson was also outside its scope."""
        from apps.entitlements import resolver
        from apps.entitlements.models import Subscription

        subscription = _start(student, trial_days=14)
        Subscription.objects.filter(pk=subscription.pk).update(trial_end=timezone.now())
        monkeypatch.setattr(resolver, "trial_covers", lambda **_: False)

        assert _resolve(student, lesson).reason == "TRIAL_EXPIRED"
