"""The RFC 9457 Problem Details error shape.

architecture.md 6.1 requires one error shape everywhere so the frontend has one
error component, and its own note on M1 says retrofitting this means touching
every frontend error handler. That is why this is the one part of M1 tested to
every branch.

The document members are exactly those the design document specifies —
``type``, ``title``, ``status``, ``detail``, ``errors`` — and no more. RFC 9457
also defines ``instance``; it is deliberately omitted rather than quietly
added, so the shape matches the document that the generated TypeScript is
checked against.
"""

from __future__ import annotations

from typing import Any

from rest_framework import exceptions, status


def _handle(exc: Exception) -> Any:
    from apps.core.exceptions import problem_details_exception_handler

    return problem_details_exception_handler(exc, {"view": None, "request": None})


class TestDocumentShape:
    def test_carries_the_five_documented_members_and_no_others(self) -> None:
        response = _handle(exceptions.ValidationError({"email": ["Enter a valid email."]}))

        assert set(response.data) == {"type", "title", "status", "detail", "errors"}

    def test_status_member_matches_the_http_status(self) -> None:
        response = _handle(exceptions.NotFound())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["status"] == status.HTTP_404_NOT_FOUND

    def test_type_defaults_to_about_blank(self) -> None:
        """RFC 9457: absent a more specific problem type URI, `about:blank`
        means the title is simply the status phrase."""
        response = _handle(exceptions.NotFound())

        assert response.data["type"] == "about:blank"

    def test_title_is_the_status_phrase_when_the_type_is_about_blank(self) -> None:
        """RFC 9457 4.2.1: `about:blank` means the title is the status phrase.
        Typed problems title the *type* instead — see TestProblemTypes."""
        assert _handle(exceptions.NotFound()).data["title"] == "Not Found"
        assert _handle(exceptions.MethodNotAllowed("POST")).data["title"] == "Method Not Allowed"
        assert _handle(exceptions.Throttled(wait=1)).data["title"] == "Too Many Requests"

    def test_content_type_is_problem_json(self) -> None:
        """Lets a client distinguish an error document from a payload without
        inspecting the body."""
        response = _handle(exceptions.NotFound())

        assert response.content_type == "application/problem+json"


class TestStatusCoverage:
    """Every code architecture.md 6.3 lists that DRF can raise."""

    def test_unauthenticated_is_401(self) -> None:
        assert _handle(exceptions.NotAuthenticated()).status_code == 401

    def test_permission_denied_is_403(self) -> None:
        assert _handle(exceptions.PermissionDenied()).status_code == 403

    def test_not_found_is_404(self) -> None:
        assert _handle(exceptions.NotFound()).status_code == 404

    def test_method_not_allowed_is_405(self) -> None:
        assert _handle(exceptions.MethodNotAllowed("POST")).status_code == 405

    def test_django_http404_is_translated_to_404(self) -> None:
        """Http404 is not a DRF exception; the handler must still produce the
        documented shape rather than Django's HTML page."""
        from django.http import Http404

        response = _handle(Http404())

        assert response.status_code == 404
        assert response.data["type"] == "about:blank"

    def test_django_permission_denied_is_translated_to_403(self) -> None:
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied

        response = _handle(DjangoPermissionDenied())

        assert response.status_code == 403


class TestValidationErrors:
    def test_field_errors_become_the_errors_map(self) -> None:
        response = _handle(
            exceptions.ValidationError({"email": ["Enter a valid email."], "age": ["Too low."]})
        )

        assert response.status_code == 400
        assert response.data["errors"] == {
            "email": ["Enter a valid email."],
            "age": ["Too low."],
        }

    def test_a_bare_list_becomes_non_field_errors(self) -> None:
        """`raise ValidationError(["..."])` carries no field name."""
        response = _handle(exceptions.ValidationError(["Passwords do not match."]))

        assert response.data["errors"] == {"non_field_errors": ["Passwords do not match."]}

    def test_a_single_string_is_wrapped_in_a_list(self) -> None:
        """The frontend must never branch on whether a value is a string or a
        list; every entry is a list."""
        response = _handle(exceptions.ValidationError({"email": "Required."}))

        assert response.data["errors"] == {"email": ["Required."]}

    def test_nested_serializer_errors_are_flattened_to_strings(self) -> None:
        response = _handle(exceptions.ValidationError({"profile": {"timezone": ["Unknown."]}}))
        errors = response.data["errors"]

        assert list(errors) == ["profile"]
        assert all(isinstance(message, str) for message in errors["profile"])

    def test_no_error_detail_objects_survive(self) -> None:
        """DRF's ErrorDetail is a str subclass carrying a `code`. Leaving them
        in place leaks the code through some serialisers and confuses the
        generated TypeScript."""
        from rest_framework.exceptions import ErrorDetail

        response = _handle(exceptions.ValidationError({"email": ["Enter a valid email."]}))

        for messages in response.data["errors"].values():
            for message in messages:
                assert type(message) is str
                assert not isinstance(message, ErrorDetail)

    def test_errors_is_absent_for_non_validation_failures(self) -> None:
        """A 404 has no field errors, and an empty map would invite the
        frontend to render an empty list."""
        response = _handle(exceptions.NotFound())

        assert response.data["errors"] is None


class TestThrottling:
    def test_throttled_is_429(self) -> None:
        assert _handle(exceptions.Throttled(wait=30)).status_code == 429

    def test_retry_after_header_is_preserved(self) -> None:
        """architecture.md 6.3 requires 429 to carry Retry-After. DRF's own
        handler sets it; this asserts wrapping it has not dropped it."""
        response = _handle(exceptions.Throttled(wait=30))

        assert response["Retry-After"] == "30"


class TestProblemTypes:
    """ADR-004. The client branches on `type`, not on the status code.

    The set is deliberately small. A type earns its place only where the status
    code is genuinely ambiguous; adding one everywhere would turn every status
    into two things a client must know about, for no gain.
    """

    def test_unauthenticated_and_forbidden_are_distinguishable(self) -> None:
        """The reason this decision exists.

        DRF downgrades NotAuthenticated to 403 when no authenticator offers a
        WWW-Authenticate header, and SessionAuthentication offers none. Without
        a type, "log in" and "you may not do that" reach the client
        identically.
        """
        unauthenticated = _handle(exceptions.NotAuthenticated())
        forbidden = _handle(exceptions.PermissionDenied())

        assert unauthenticated.data["type"] == "/problems/not-authenticated"
        assert forbidden.data["type"] == "/problems/permission-denied"
        assert unauthenticated.data["type"] != forbidden.data["type"]

    def test_a_typed_problem_titles_the_type_not_the_status(self) -> None:
        """RFC 9457 3.1.1: title summarises the problem *type*."""
        assert _handle(exceptions.NotAuthenticated()).data["title"] == "Authentication required"
        assert _handle(exceptions.PermissionDenied()).data["title"] == "Permission denied"

    def test_django_permission_denied_maps_to_the_same_type(self) -> None:
        """Raised by Django's own decorators, and must not look different."""
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied

        response = _handle(DjangoPermissionDenied())

        assert response.data["type"] == "/problems/permission-denied"

    def test_ordinary_failures_stay_about_blank(self) -> None:
        """A 404 or a 429 needs no type: the status says everything."""
        assert _handle(exceptions.NotFound()).data["type"] == "about:blank"
        assert _handle(exceptions.Throttled(wait=1)).data["type"] == "about:blank"
        assert _handle(exceptions.ValidationError(["bad"])).data["type"] == "about:blank"

    def test_an_exception_may_declare_its_own_type(self) -> None:
        """The extension point M4 needs.

        `EntitlementDenied` will set these attributes and add `reason` and
        `cta`, without the handler changing.
        """

        class SubscriptionRequired(exceptions.PermissionDenied):
            problem_type = "/problems/subscription-required"
            problem_title = "Subscription required"

        response = _handle(SubscriptionRequired())

        assert response.data["type"] == "/problems/subscription-required"
        assert response.data["title"] == "Subscription required"


class TestDefensiveFallback:
    def test_a_scalar_payload_becomes_the_detail(self) -> None:
        """Tested directly because DRF cannot currently reach it.

        DRF wraps any non-list, non-dict detail in `{"detail": ...}` before the
        handler sees it, so this branch is unreachable through the normal path.
        It stays because an exception handler that raises while handling an
        exception is the worst failure mode available: the original error is
        lost and the client gets a 500 with no diagnosis.
        """
        from apps.core.exceptions import _split

        detail, errors = _split("something unexpected")

        assert detail == "something unexpected"
        assert errors is None


class TestUnhandledExceptions:
    def test_returns_none_so_django_reports_the_error(self) -> None:
        """A non-API exception is a bug, not a client error.

        Returning None lets it propagate to Django's 500 handling, which is
        what error tracking hooks into. Converting it here would produce a
        tidier body at the cost of losing the report — and the frontend needs a
        non-JSON fallback regardless, since a gateway timeout is never JSON.
        """
        assert _handle(ValueError("a genuine bug")) is None

    def test_does_not_convert_a_database_error(self) -> None:
        from django.db import DatabaseError

        assert _handle(DatabaseError("connection lost")) is None
