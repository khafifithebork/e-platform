"""The refund service, which deliberately does not refund anything yet.

Spec §2.2 and ADR-018 §3 settled this: M10 builds the permission check, the
validation and the refusal paths; the provider call is M8's. Writing a fake
that answered *whether partial refunds exist*, *whether there is a window*,
*whether an idempotency key is mandatory* and *whether the result arrives by
webhook* would invent a provider capability, which §6 forbids — and every test
against it would be confidence in behaviour nobody has verified.

So the assertions here are about a gap, and they are written to fail the day
somebody closes it carelessly. `test_it_writes_no_audit_row` is the one worth
reading: a refund that raised did not happen, and a row describing an action
that did not happen is a false record. The suite already refuses that shape for
course approval; this holds the same line for money.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.core.models import AuditLog
from apps.entitlements.models import Subscription
from apps.entitlements.services import InvalidRefund, RefundNotAvailable, issue_refund

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str):
    from apps.accounts.services import create_account

    return create_account(email=email, password=PASSWORD)


@pytest.fixture
def admin(db):
    from apps.accounts.models import Role

    user = _user("admin@example.test")
    user.role = Role.ADMIN
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def subscription(db) -> Subscription:
    learner = _user("learner@example.test")
    call_command("billing", "start", email=learner.email, stdout=StringIO())
    return Subscription.objects.get(user=learner)


class TestTheGapIsVisible:
    def test_it_raises_rather_than_pretending(self, admin, subscription) -> None:
        """A service that answered "done" while moving no money would be the
        worst available outcome: support tells a learner they were refunded,
        and nothing ever reaches their card."""
        with pytest.raises(RefundNotAvailable):
            issue_refund(actor=admin, subscription=subscription, reason="Double charged in July")

    def test_the_message_names_what_is_missing(self, admin, subscription) -> None:
        """The exception is read by a person deciding what to do next, so it
        says which milestone owns the missing half rather than "not
        implemented"."""
        with pytest.raises(RefundNotAvailable) as raised:
            issue_refund(actor=admin, subscription=subscription, reason="Double charged")

        assert "M8" in str(raised.value)

    def test_it_writes_no_audit_row(self, admin, subscription) -> None:
        """The whole of T8's audit decision, in one assertion. `REFUND_ISSUED`
        stays in the closed vocabulary as the marker; nothing writes it yet,
        because nothing has happened to record."""
        with pytest.raises(RefundNotAvailable):
            issue_refund(actor=admin, subscription=subscription, reason="Double charged")

        assert not AuditLog.objects.exists()

    def test_it_changes_no_subscription_state(self, admin, subscription) -> None:
        """A refund is not a cancellation. Revoking access here would be a
        half-done refund — the learner loses the content and keeps the
        charge — which is worse than refusing outright."""
        before = (subscription.status, subscription.current_period_end)

        with pytest.raises(RefundNotAvailable):
            issue_refund(actor=admin, subscription=subscription, reason="Double charged")

        subscription.refresh_from_db()
        assert (subscription.status, subscription.current_period_end) == before

    def test_and_no_subscription_event_is_logged(self, admin, subscription) -> None:
        """The twin for the assertion above: an event row would say something
        happened to this subscription, and nothing did."""
        from apps.entitlements.models import SubscriptionEvent

        before = SubscriptionEvent.objects.filter(subscription=subscription).count()

        with pytest.raises(RefundNotAvailable):
            issue_refund(actor=admin, subscription=subscription, reason="Double charged")

        assert SubscriptionEvent.objects.filter(subscription=subscription).count() == before


class TestItValidatesBeforeItGivesUp:
    """Ordering, and it is the point of the task rather than a detail.

    M8 adds a provider call where the refusal is. Everything checked *above*
    that line is inherited; anything checked below it would have to be written
    beside a live payments integration, which ADR-018 §3 names as the thing to
    avoid.
    """

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t "])
    def test_a_blank_reason_is_refused_as_invalid(self, admin, subscription, reason: str) -> None:
        """`InvalidRefund`, not `RefundNotAvailable`. If this raised the latter
        the validation would be untested today and unwritten tomorrow.

        Checked in the service and not only the serializer because this is
        reachable from a management command, where no serializer runs — the
        same reason `grant_access_override` repeats its own check."""
        with pytest.raises(InvalidRefund):
            issue_refund(actor=admin, subscription=subscription, reason=reason)

    def test_an_action_with_no_actor_is_refused(self, subscription) -> None:
        """M8 writes an audit row here, and `record_admin_action` refuses one
        that cannot name who acted. Checking it now means the refund service
        does not learn that rule for the first time next to a live provider."""
        with pytest.raises(InvalidRefund):
            issue_refund(actor=None, subscription=subscription, reason="Double charged")

    def test_and_a_complete_request_gets_past_validation(self, admin, subscription) -> None:
        """The positive twin. A service that raised `InvalidRefund`
        unconditionally would satisfy every test above."""
        with pytest.raises(RefundNotAvailable):
            issue_refund(actor=admin, subscription=subscription, reason="Double charged")
