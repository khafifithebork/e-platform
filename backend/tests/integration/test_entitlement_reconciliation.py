"""Entitlement reconciliation. M14 T3, abuse cases 3, 4 and 7.

ADR-002 §4 rates this job above paid redundancy and it was never written. What
it is for is concrete, and the resolver says so itself. ``_decide_for`` allows
an ACTIVE subscription **without checking the period**, on these grounds:

    "A stale ACTIVE row past its period is the expiry sweep's job; denying here
    instead would lock out a paying customer whenever a renewal event is late"

That reasoning is right, and it assumes a sweep exists. **None does.** So an
ACTIVE row whose renewal never arrived serves paid content indefinitely and
nothing anywhere notices. ``TestItFindsAccessItShouldNot`` is that case.

The three abuse cases are the reason the tests below are shaped as they are:

- **3 — reports, does not repair.** Proven by comparing rows before and after,
  not by reading the source for an absent ``.save()``.
- **4 — read-only, provably.** Proven by capturing the SQL the command issues
  and asserting no statement writes.
- **7 — no fan-out.** Proven per ADR-009: two dataset sizes, identical query
  counts. A measurement at one size cannot tell a constant from a linear.
"""

from __future__ import annotations

import io
import json
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.entitlements.models import Subscription, SubscriptionEvent, SubscriptionStatus
from apps.entitlements.selectors import FINDING_EXAMPLES, reconciliation_findings

pytestmark = pytest.mark.django_db

WRITE_STATEMENTS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "ALTER", "DROP")
PASSWORD = "a-long-enough-passphrase"


def _user(email: str, role: str = Role.STUDENT) -> User:
    user = User.objects.create_user(email=email, password=PASSWORD)
    user.role = role
    user.save(update_fields=["role"])
    return user


def _subscription(email: str, status: str, *, period_end, trial_end=None) -> Subscription:
    return Subscription.objects.create(
        user=_user(email),
        status=status,
        current_period_end=period_end,
        trial_end=trial_end,
        provider="fake",
    )


def _lapsed(email: str = "lapsed@example.test") -> Subscription:
    """The headline case: ACTIVE, three days past the period it was paid for."""
    return _subscription(
        email,
        SubscriptionStatus.ACTIVE,
        period_end=timezone.now() - timedelta(days=3),
    )


def _codes(findings) -> set[str]:
    return {finding.code for finding in findings}


def _by_code(findings, code: str):
    return next(finding for finding in findings if finding.code == code)


def _writes(captured: CaptureQueriesContext) -> list[str]:
    return [
        query["sql"]
        for query in captured.captured_queries
        if query["sql"].lstrip().upper().startswith(WRITE_STATEMENTS)
    ]


class TestItFindsAccessItShouldNot:
    """The category that costs money, and the reason the job exists."""

    def test_an_active_row_past_its_period_is_reported(self) -> None:
        _lapsed()

        assert "ACTIVE_PAST_PERIOD" in _codes(reconciliation_findings())

    def test_and_it_is_flagged_as_granting_access(self) -> None:
        """The twin, and the more important half. Finding the row is not the
        point — telling it apart from the stale rows that grant nothing is,
        because that difference decides whether anybody is woken up."""
        _lapsed()

        assert _by_code(reconciliation_findings(), "ACTIVE_PAST_PERIOD").grants_access is True

    def test_a_current_active_row_is_not_reported(self) -> None:
        """The negative. A job that flags every ACTIVE subscription is a job
        that gets muted within a week."""
        _subscription(
            "paying@example.test",
            SubscriptionStatus.ACTIVE,
            period_end=timezone.now() + timedelta(days=20),
        )

        assert reconciliation_findings() == []


class TestThePremiseUnderneathThatCategory:
    """Not a test of reconciliation — a test of the claim it rests on.

    If the resolver denied a lapsed ACTIVE row, ``ACTIVE_PAST_PERIOD`` would be
    housekeeping like the rest and flagging it ``grants_access`` would be a
    false alarm. It does not deny it, deliberately. This pins that, so the day
    somebody adds a period check to the resolver, the reason to keep flagging
    this category disappears loudly rather than quietly.
    """

    @pytest.fixture
    def published_lesson(self, db):
        from apps.catalog.models import Course, Language, Lesson, Section
        from apps.catalog.services import approve, submit_for_review

        instructor = _user("teacher@example.test", Role.INSTRUCTOR)
        admin = _user("approver@example.test", Role.ADMIN)
        language = Language.objects.create(code="es", name="Spanish", native_name="Español")
        course = Course.objects.create(
            slug="spanish",
            title="Spanish",
            language=language,
            level="A1",
            instructor=instructor,
        )
        section = Section.objects.create(course=course, title="Greetings", position=1)
        lesson = Lesson.objects.create(
            course=course,
            section=section,
            slug="intro",
            title="Intro",
            body="Hola.",
            position=1,
        )
        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin)
        return lesson

    def test_the_resolver_really_does_still_grant_a_lapsed_active_row(
        self, published_lesson
    ) -> None:
        from apps.entitlements.resolver import resolve_access

        subscription = _lapsed()

        decision = resolve_access(user=subscription.user, lesson=published_lesson)

        assert decision.allowed is True


class TestItSeparatesStaleFromDangerous:
    """Rows the resolver already refuses. Worth reporting, not worth paging."""

    def test_a_trialing_row_past_its_end_is_reported_as_harmless(self) -> None:
        past = timezone.now() - timedelta(days=2)
        _subscription(
            "trial@example.test",
            SubscriptionStatus.TRIALING,
            period_end=past,
            trial_end=past,
        )

        assert _by_code(reconciliation_findings(), "TRIALING_PAST_END").grants_access is False

    def test_a_past_due_row_beyond_grace_is_reported_as_harmless(self) -> None:
        beyond = timezone.now() - timedelta(days=settings.ENTITLEMENT_GRACE_PERIOD_DAYS + 2)
        _subscription("late@example.test", SubscriptionStatus.PAST_DUE, period_end=beyond)

        assert _by_code(reconciliation_findings(), "PAST_DUE_BEYOND_GRACE").grants_access is False

    def test_a_past_due_row_inside_grace_is_not_reported(self) -> None:
        """The negative that makes the one above mean something. Grace exists
        so a late payment does not cut access off, and reporting rows inside it
        would be reporting normal operation."""
        _subscription(
            "late@example.test",
            SubscriptionStatus.PAST_DUE,
            period_end=timezone.now() - timedelta(days=1),
        )

        assert reconciliation_findings() == []

    def test_a_canceled_row_past_its_period_is_reported_as_harmless(self) -> None:
        _subscription(
            "gone@example.test",
            SubscriptionStatus.CANCELED,
            period_end=timezone.now() - timedelta(days=5),
        )

        assert _by_code(reconciliation_findings(), "CANCELED_PAST_PERIOD").grants_access is False

    def test_a_canceled_row_inside_its_period_is_not_reported(self) -> None:
        """Cancelling keeps access until the period ends — that is the product
        working, and ADR-010 is why CANCELED is absent from LIVE_STATUSES."""
        _subscription(
            "leaving@example.test",
            SubscriptionStatus.CANCELED,
            period_end=timezone.now() + timedelta(days=9),
        )

        assert reconciliation_findings() == []

    def test_an_expired_row_is_never_reported(self) -> None:
        """EXPIRED is terminal, and every expired subscription is past its
        period by definition. Reporting them would mean reporting the entire
        history of the product, forever, growing every day."""
        _subscription(
            "old@example.test",
            SubscriptionStatus.EXPIRED,
            period_end=timezone.now() - timedelta(days=400),
        )

        assert reconciliation_findings() == []


class TestItReportsAndDoesNotRepair:
    """Abuse case 3. Invariant 3 has exactly one writer of subscription state.

    Asserted against the rows rather than against the source, because "there is
    no ``.save()`` in the file" is a claim about today's code and this is a
    claim about behaviour.
    """

    def test_the_drifted_row_is_left_exactly_as_it_was(self) -> None:
        subscription = _lapsed()
        before = (subscription.status, subscription.current_period_end, subscription.updated_at)

        with pytest.raises(SystemExit):
            call_command("reconcile_entitlements", stdout=io.StringIO())

        subscription.refresh_from_db()

        assert (
            subscription.status,
            subscription.current_period_end,
            subscription.updated_at,
        ) == before

    def test_running_it_twice_reports_the_same_thing(self) -> None:
        """A repairing job reports drift once and then reports nothing, which
        from the outside is indistinguishable from a job that found nothing.
        This is what tells the two apart."""
        _lapsed()

        first = reconciliation_findings()
        second = reconciliation_findings()

        assert _codes(first) == _codes(second) == {"ACTIVE_PAST_PERIOD"}

    def test_no_subscription_event_is_written(self) -> None:
        """The subtler repair. Recording that drift was *seen* is still a
        write, and ``SubscriptionEvent`` is the lifecycle's audit trail —
        putting an observer's rows into it would make the history of a
        subscription depend on how often a cron job ran."""
        _lapsed()
        before = SubscriptionEvent.objects.count()

        with pytest.raises(SystemExit):
            call_command("reconcile_entitlements", stdout=io.StringIO())

        assert SubscriptionEvent.objects.count() == before


class TestItIsReadOnly:
    """Abuse case 4 — "provably", which means looking at the SQL."""

    def test_it_issues_no_write_statement(self) -> None:
        _lapsed()

        with CaptureQueriesContext(connection) as captured:
            reconciliation_findings()

        assert _writes(captured) == []

    def test_the_check_would_notice_a_write(self) -> None:
        """The provocation, inline. A filter that matches nothing passes the
        test above whatever the command does, so the filter is shown catching a
        real write before it is trusted to prove an absence."""
        with CaptureQueriesContext(connection) as captured:
            _lapsed("written@example.test")

        assert _writes(captured)


class TestItDoesNotFanOut:
    """Abuse case 7, measured the way ADR-009 requires: two dataset sizes,
    identical counts."""

    @staticmethod
    def _drifted(count: int, offset: int = 0) -> None:
        stale = timezone.now() - timedelta(days=3)
        for index in range(count):
            _subscription(
                f"lapsed{offset + index}@example.test",
                SubscriptionStatus.ACTIVE,
                period_end=stale,
            )

    def test_the_query_count_does_not_grow_with_the_data(self) -> None:
        self._drifted(3)
        with CaptureQueriesContext(connection) as small:
            reconciliation_findings()

        self._drifted(30, offset=100)
        with CaptureQueriesContext(connection) as large:
            reconciliation_findings()

        assert len(large.captured_queries) == len(small.captured_queries)

    def test_the_examples_are_capped(self) -> None:
        """The other half of not fanning out: an alert carrying every id is an
        alert nobody opens. The ids exist so somebody can go and look at one,
        not so the alert can be exhaustive."""
        self._drifted(FINDING_EXAMPLES + 6)

        finding = _by_code(reconciliation_findings(), "ACTIVE_PAST_PERIOD")

        assert finding.count == FINDING_EXAMPLES + 6
        assert len(finding.examples) == FINDING_EXAMPLES


class TestTheCommandsExitCodes:
    """Split three ways because a scheduler reads them before a person does."""

    def test_a_clean_database_exits_zero(self) -> None:
        _subscription(
            "paying@example.test",
            SubscriptionStatus.ACTIVE,
            period_end=timezone.now() + timedelta(days=20),
        )

        call_command("reconcile_entitlements", stdout=io.StringIO())

    def test_drift_that_grants_access_exits_one(self) -> None:
        _lapsed()

        with pytest.raises(SystemExit) as exit_info:
            call_command("reconcile_entitlements", stdout=io.StringIO())

        assert exit_info.value.code == 1

    def test_drift_that_grants_nothing_exits_two(self) -> None:
        """The distinction the exit-code split exists for. Collapsing these
        into one non-zero code would page somebody at 3am for a stale CANCELED
        row that is refusing access correctly."""
        _subscription(
            "gone@example.test",
            SubscriptionStatus.CANCELED,
            period_end=timezone.now() - timedelta(days=5),
        )

        with pytest.raises(SystemExit) as exit_info:
            call_command("reconcile_entitlements", stdout=io.StringIO())

        assert exit_info.value.code == 2

    def test_the_json_output_parses(self) -> None:
        """T4 consumes this. A human-readable report that an alert has to
        scrape is a format which breaks the day somebody improves the
        wording."""
        _lapsed()
        out = io.StringIO()

        with pytest.raises(SystemExit):
            call_command("reconcile_entitlements", "--json", stdout=out)

        payload = json.loads(out.getvalue())

        assert payload[0]["code"] == "ACTIVE_PAST_PERIOD"
        assert payload[0]["grants_access"] is True

    def test_the_output_carries_no_email_address(self) -> None:
        """§6 case 6. This text is destined for a mailbox nobody audits, and a
        ``Subscription`` reaches a ``User`` in one hop — printing the owner
        would be the obvious convenience and the wrong one."""
        _lapsed()
        out = io.StringIO()

        with pytest.raises(SystemExit):
            call_command("reconcile_entitlements", stdout=out)

        assert "lapsed@example.test" not in out.getvalue()

    def test_the_json_output_carries_no_email_address_either(self) -> None:
        """The twin. The machine-readable format is the one an alert actually
        embeds, so covering only the human one would guard the wrong path."""
        _lapsed()
        out = io.StringIO()

        with pytest.raises(SystemExit):
            call_command("reconcile_entitlements", "--json", stdout=out)

        assert "lapsed@example.test" not in out.getvalue()


class TestTheConstraintCheck:
    def test_a_healthy_database_reports_no_duplicates(self) -> None:
        """The constraint makes duplicates impossible, so the honest test of
        this category is that it stays quiet. A check that fires on a healthy
        database is noise, and the drift it looks for cannot be manufactured
        without dropping the constraint first."""
        _subscription(
            "paying@example.test",
            SubscriptionStatus.ACTIVE,
            period_end=timezone.now() + timedelta(days=20),
        )

        assert "MULTIPLE_LIVE_SUBSCRIPTIONS" not in _codes(reconciliation_findings())

    def test_it_fires_when_the_constraint_is_not_there(self) -> None:
        """The provocation, and it needs the real thing.

        Every other category can be manufactured by writing a row. This one
        cannot: the constraint refuses it. So the constraint is dropped inside
        the test transaction — pytest-django rolls the whole thing back, and
        the check is shown catching the drift it claims to catch rather than
        being trusted because it looks right.

        Without this the category is a query nobody has ever seen return a row,
        which is indistinguishable from a query that cannot.
        """
        user = _user("double@example.test")
        now = timezone.now()

        with connection.cursor() as cursor:
            # DROP INDEX, not ALTER TABLE DROP CONSTRAINT. A UniqueConstraint
            # with a `condition` is a *partial unique index* in Postgres and
            # not a table constraint at all — dropping the constraint by name
            # succeeds, changes nothing, and the insert below still fails.
            # Observed while writing this test, not assumed.
            cursor.execute("DROP INDEX one_live_subscription_per_user")

        for _ in range(2):
            Subscription.objects.create(
                user=user,
                status=SubscriptionStatus.ACTIVE,
                current_period_end=now + timedelta(days=20),
                provider="fake",
            )

        finding = _by_code(reconciliation_findings(), "MULTIPLE_LIVE_SUBSCRIPTIONS")

        assert finding.count == 1
        assert finding.grants_access is True

    def test_the_constraint_is_still_there(self) -> None:
        """Which is the assumption the test above rests on. If the constraint
        were dropped, "no duplicates found" would mean nothing at all."""
        constraints = {constraint.name for constraint in Subscription._meta.constraints}

        assert "one_live_subscription_per_user" in constraints
