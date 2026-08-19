"""The refusal as the client sees it.

ADR-004 settled that clients branch on the Problem Details `type`, because DRF
downgrades 401 to 403 under session authentication and the status alone cannot
distinguish "log in" from "not allowed". An entitlement denial is the case that
decision was made for: every refusal here is a 403, so the type and the reason
are the only things carrying meaning.

These strings are the API contract. Renaming one breaks any client branching on
it, which is why they are asserted literally rather than compared to the
constants that produce them — a test importing the same enum it checks would
pass through a rename and let the break reach the frontend.
"""

from __future__ import annotations

import pytest
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_default_handler

from apps.core.exceptions import problem_details_exception_handler
from apps.entitlements.exceptions import EntitlementDenied
from apps.entitlements.resolver import AccessDecision, Cta, Reason


def _render(exc: Exception) -> dict:
    """Put an exception through the real handler and read the document."""
    response = problem_details_exception_handler(exc, {})
    assert response is not None, "the handler declined to render this"
    return response.data


class TestTheDocument:
    def test_a_denial_renders_as_problem_details_with_a_reason(self) -> None:
        decision = AccessDecision(False, Reason.NO_SUBSCRIPTION, Cta.SUBSCRIBE)

        document = _render(EntitlementDenied(decision))

        assert document["type"] == "/problems/entitlement-denied"
        assert document["status"] == 403
        assert document["reason"] == "NO_SUBSCRIPTION"
        assert document["cta"] == "subscribe"

    @pytest.mark.parametrize(
        ("reason", "cta"),
        [
            (Reason.LOGIN_REQUIRED, Cta.LOGIN),
            (Reason.NO_SUBSCRIPTION, Cta.SUBSCRIBE),
            (Reason.SUBSCRIPTION_EXPIRED, Cta.SUBSCRIBE),
            (Reason.TRIAL_EXPIRED, Cta.SUBSCRIBE),
            (Reason.TRIAL_SCOPE, Cta.SUBSCRIBE),
            (Reason.GRACE_PERIOD_ENDED, Cta.UPDATE_PAYMENT),
        ],
    )
    def test_every_denial_reason_survives_the_round_trip(self, reason, cta) -> None:
        """Each reason the resolver can refuse with must arrive intact. A
        reason lost between the resolver and the wire is a frontend that
        cannot tell a failed card from a missing subscription."""
        document = _render(EntitlementDenied(AccessDecision(False, reason, cta)))

        assert document["reason"] == str(reason)
        assert document["cta"] == cta

    def test_the_type_is_the_same_for_every_reason(self) -> None:
        """One type, many reasons. A type per reason would make every new
        reason a breaking change for any client matching on unknown types."""
        expired = _render(EntitlementDenied(AccessDecision(False, Reason.TRIAL_EXPIRED, "x")))
        none = _render(EntitlementDenied(AccessDecision(False, Reason.NO_SUBSCRIPTION, "y")))

        assert expired["type"] == none["type"]

    def test_login_required_is_a_403_not_a_401(self) -> None:
        """Not an oversight. §6.3 specifies 403 for entitlement denial, and DRF
        downgrades 401 to 403 anyway when no authenticator offers a
        WWW-Authenticate header — SessionAuthentication offers none (ADR-004).
        The status would be 403 regardless, so the reason carries the meaning."""
        document = _render(
            EntitlementDenied(AccessDecision(False, Reason.LOGIN_REQUIRED, Cta.LOGIN))
        )

        assert document["status"] == 403
        assert document["reason"] == "LOGIN_REQUIRED"


class TestTheHandlerIsNotWeakened:
    def test_extension_members_cannot_overwrite_standard_ones(self) -> None:
        """An exception that could rewrite `status` or `type` could make a 403
        describe itself as something else, and clients branch on both."""

        class Liar(APIException):
            status_code = 403
            default_detail = "no"

        liar = Liar()
        liar.extensions = {"status": 200, "type": "/problems/fine", "reason": "SNEAKY"}

        document = _render(liar)

        assert document["status"] == 403
        assert document["type"] != "/problems/fine"
        # A genuine extension still lands — the guard is on collisions only.
        assert document["reason"] == "SNEAKY"

    def test_exceptions_without_extensions_are_unaffected(self) -> None:
        """Everything from M1 and M2 renders exactly as before."""
        from rest_framework.exceptions import NotFound

        document = _render(NotFound())

        assert document["status"] == 404
        assert "reason" not in document

    def test_the_handler_still_declines_what_drf_declines(self) -> None:
        """Non-API exceptions must reach the 500 path, not be dressed up as a
        Problem Details document."""
        assert drf_default_handler(RuntimeError("boom"), {}) is None
        assert problem_details_exception_handler(RuntimeError("boom"), {}) is None


class TestTheExceptionRefusesToLie:
    def test_it_cannot_be_built_from_an_allowance(self) -> None:
        """An inverted condition at a call site would otherwise show a 403 to
        somebody who has paid, and the document would cheerfully say
        `reason: SUBSCRIPTION_ACTIVE`."""
        allowed = AccessDecision(True, Reason.SUBSCRIPTION_ACTIVE)

        with pytest.raises(ValueError, match="requires a denial"):
            EntitlementDenied(allowed)


class TestThePermissionClass:
    """It must raise, not return False.

    Returning False produces DRF's generic 403 with no reason, which pushes the
    decision of what to offer the user back into the frontend — entitlement
    logic in a second place, which is what invariant 3 forbids.
    """

    def _check(self, user, lesson):
        from apps.entitlements.permissions import IsEntitledToLesson

        request = type("Request", (), {"user": user})()
        return IsEntitledToLesson().has_object_permission(request, None, lesson)

    @pytest.mark.django_db
    def test_a_denial_raises_with_the_resolvers_reason(self, db) -> None:
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Language, Lesson, Section

        student = create_account(email="student@example.test", password="a-long-passphrase")
        instructor = create_account(email="teacher@example.test", password="a-long-passphrase")
        language = Language.objects.create(code="es", name="Spanish", native_name="Español")
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="Greetings", position=1)
        lesson = Lesson.objects.create(
            course=course, section=section, slug="intro", title="Intro", position=1
        )

        with pytest.raises(EntitlementDenied) as raised:
            self._check(student, lesson)

        assert raised.value.extensions["reason"] == "NO_SUBSCRIPTION"

    @pytest.mark.django_db
    def test_an_allowance_returns_true(self, db) -> None:
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Language, Lesson, Section

        instructor = create_account(email="teacher@example.test", password="a-long-passphrase")
        language = Language.objects.create(code="es", name="Spanish", native_name="Español")
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="Greetings", position=1)
        lesson = Lesson.objects.create(
            course=course,
            section=section,
            slug="intro",
            title="Intro",
            position=1,
            is_preview=True,
        )

        assert self._check(instructor, lesson) is True
