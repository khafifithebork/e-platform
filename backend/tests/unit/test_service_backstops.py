"""The guards that only a non-API caller can reach.

T2 measured §8.1 and found every target met. What it also found was three
uncovered spots sharing one shape, and that shape is the point of this file:
**a check written as a backstop, tested only through the path that makes it
unreachable.**

`grant_access_override` refuses a bad duration and a blank reason. There are
tests for both refusals — and both go through the API, where the serializer
rejects first, so the service's own checks never execute. The docstring says
they exist "because the service is reachable from a management command where no
serializer runs". Nothing was calling it that way.

That is not a coverage statistic. It is a control that would have been deleted
in a refactor with a green suite, and the deletion would only surface the first
time somebody granted an override from a shell.
"""

from __future__ import annotations

import pytest

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


def _user(email: str, *, role=None):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    if role:
        user.role = role
        user.save(update_fields=["role"])
    return user


class TestTheOverrideGuardsWithoutASerializer:
    """Called directly, the way a management command would."""

    def test_a_duration_below_one_day_is_refused(self, settings) -> None:
        from apps.accounts.models import Role
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(actor=admin, user=learner, days=0, reason="Because")

    def test_a_duration_above_the_maximum_is_refused(self, settings) -> None:
        from apps.accounts.models import Role
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(
                actor=admin,
                user=learner,
                days=settings.ACCESS_OVERRIDE_MAX_DAYS + 1,
                reason="Because",
            )

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
    def test_a_blank_reason_is_refused(self, reason: str) -> None:
        from apps.accounts.models import Role
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(actor=admin, user=learner, days=7, reason=reason)

    def test_and_nothing_is_written_when_it_refuses(self) -> None:
        """The twin. A guard that raised *after* creating the row would satisfy
        every test above and still leave an unexplained override behind."""
        from apps.accounts.models import Role
        from apps.core.models import AuditLog
        from apps.entitlements.models import AccessOverride
        from apps.entitlements.services import InvalidOverride, grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        with pytest.raises(InvalidOverride):
            grant_access_override(actor=admin, user=learner, days=7, reason="  ")

        assert not AccessOverride.objects.exists()
        assert not AuditLog.objects.exists()

    def test_but_a_valid_grant_still_works(self) -> None:
        """The positive twin. A service that refused everything would pass all
        four assertions above."""
        from apps.accounts.models import Role
        from apps.entitlements.models import AccessOverride
        from apps.entitlements.services import grant_access_override

        admin = _user("admin@example.test", role=Role.ADMIN)
        learner = _user("learner@example.test")

        grant_access_override(actor=admin, user=learner, days=7, reason="Double charged")

        assert AccessOverride.objects.count() == 1


class TestATrialSurvivesATransition:
    """`trial_end` is not lost when a trialing subscription moves on.

    **This does not cover `_apply`'s carry-forward branch, and the first
    version of this docstring said it did.** Measured afterwards: the line
    stayed uncovered. `trial_end` survives a renewal because `_apply` leaves
    the field alone when the provider's snapshot carries no trial end — not
    because the assignment ran.

    The branch needs a snapshot *with* a `trial_end` arriving through `_apply`,
    and `FakeBillingProvider.renew_subscription` never sets one. It is
    unreachable through the only provider that exists, and reaching it would
    mean teaching the fake to report something no real provider has been
    observed doing — §6's invention, in test clothing. **M8 covers it**, with a
    provider whose renewal payload is a fact rather than a guess.

    The behaviour below is still worth pinning: a renewal that cleared the
    column would fail it, and that is the failure support would feel.
    """

    def test_the_trial_end_is_kept_after_the_trial_converts(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        from apps.entitlements.models import Subscription

        learner = _user("learner@example.test")
        call_command("billing", "start", email=learner.email, trial_days=14, stdout=StringIO())

        subscription = Subscription.objects.get(user=learner)
        assert subscription.trial_end is not None
        started_with = subscription.trial_end

        call_command("billing", "renew", email=learner.email, stdout=StringIO())

        subscription.refresh_from_db()
        assert subscription.trial_end == started_with, "the trial end was cleared or moved"

    def test_and_the_status_actually_moved(self) -> None:
        """The twin. A renewal that silently did nothing would preserve
        `trial_end` perfectly."""
        from io import StringIO

        from django.core.management import call_command

        from apps.entitlements.models import Subscription

        learner = _user("learner@example.test")
        call_command("billing", "start", email=learner.email, trial_days=14, stdout=StringIO())
        call_command("billing", "renew", email=learner.email, stdout=StringIO())

        assert Subscription.objects.get(user=learner).status == "ACTIVE"


class TestTheLockoutReadsAFormLogin:
    """django-axes attributes a failed attempt to a username.

    `accounts/axes.py` reads `credentials` first and falls back to the posted
    form field, and the fallback exists for one reason: **Django Admin posts a
    form**, not JSON. Every test in the suite posts JSON, so the fallback — the
    half that protects the highest-value login in the system — was the
    uncovered line.
    """

    def test_a_form_post_is_attributed(self, rf) -> None:
        from apps.accounts.axes import get_username

        request = rf.post("/login/", {"email": "learner@example.test"})

        assert get_username(request, credentials=None) == "learner@example.test"

    def test_credentials_win_when_both_are_present(self, rf) -> None:
        """The authoritative source is what was passed to `authenticate()`, not
        a re-read of a body a middleware may have altered."""
        from apps.accounts.axes import get_username

        request = rf.post("/login/", {"email": "from-the-form@example.test"})

        username = get_username(request, credentials={"email": "from-credentials@example.test"})

        assert username == "from-credentials@example.test"

    def test_empty_credentials_fall_through_to_the_form(self, rf) -> None:
        """The partial branch: `credentials` is present but carries nothing
        usable. Falling through matters because django-axes would otherwise key
        the lockout on an empty username for a request that named one."""
        from apps.accounts.axes import get_username

        request = rf.post("/login/", {"email": "learner@example.test"})

        assert get_username(request, credentials={"email": ""}) == "learner@example.test"

    def test_neither_present_is_an_empty_string_rather_than_none(self, rf) -> None:
        """django-axes keys its lockout on this value. `None` and `""` are
        different keys, and a lockout keyed on `None` is a lockout shared by
        every anonymous failure."""
        from apps.accounts.axes import get_username

        assert get_username(rf.post("/login/", {}), credentials=None) == ""
