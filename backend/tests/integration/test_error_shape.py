"""The error shape as a client actually receives it.

The unit tests prove the document is built correctly. These prove it is
*wired*: that REST_FRAMEWORK["EXCEPTION_HANDLER"] points at it, that the
Content-Type survives rendering, and that the deny-by-default permission
produces a Problem Details document rather than DRF's own payload.

Views are invoked through APIRequestFactory rather than a URL conf, because the
real dispatch path — and therefore APIView.handle_exception, which is what
consults the setting — runs either way.
"""

from __future__ import annotations

import json

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()


@api_view(["GET"])
@permission_classes([AllowAny])
def raises_validation(request):
    raise ValidationError({"email": ["Enter a valid email."]})


@api_view(["GET"])
@permission_classes([AllowAny])
def raises_not_found(request):
    raise NotFound()


@api_view(["GET"])
@permission_classes([AllowAny])
def succeeds(request):
    return Response({"ok": True})


@api_view(["GET"])
def requires_authentication(request):
    return Response({"ok": True})


def _call(view, method: str = "get"):
    request = getattr(factory, method)("/probe/")
    response = view(request)
    response.render()
    return response


def _body(response) -> dict:
    return json.loads(response.content)


class TestHandlerIsWired:
    def test_validation_failure_uses_the_problem_document(self) -> None:
        response = _call(raises_validation)

        assert response.status_code == 400
        assert _body(response) == {
            "type": "about:blank",
            "title": "Bad Request",
            "status": 400,
            "detail": "Invalid input.",
            "errors": {"email": ["Enter a valid email."]},
        }

    def test_content_type_header_reaches_the_client(self) -> None:
        """Asserted on the rendered header, not the attribute — the renderer
        gets the last word on Content-Type."""
        response = _call(raises_validation)

        assert response["Content-Type"] == "application/problem+json"

    def test_not_found_uses_the_problem_document(self) -> None:
        response = _call(raises_not_found)

        assert response.status_code == 404
        assert _body(response)["title"] == "Not Found"
        assert _body(response)["errors"] is None

    def test_method_not_allowed_uses_the_problem_document(self) -> None:
        response = _call(raises_validation, method="post")

        assert response.status_code == 405
        assert _body(response)["title"] == "Method Not Allowed"


class TestSuccessIsUntouched:
    def test_a_successful_response_is_ordinary_json(self) -> None:
        """The handler must not touch responses that are not errors."""
        response = _call(succeeds)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert _body(response) == {"ok": True}


class TestDenyByDefault:
    def test_an_unauthenticated_request_is_refused_in_the_problem_shape(self) -> None:
        """Deny-by-default from T2, rendered through the handler from T3.

        On the status code: architecture.md 6.1 says 401 for unauthenticated,
        but DRF downgrades NotAuthenticated to 403 when no authenticator offers
        a WWW-Authenticate header, and SessionAuthentication offers none. This
        asserts the behaviour that actually occurs; the divergence is raised
        for decision in M2, where the auth endpoints live.
        """
        response = _call(requires_authentication)

        assert response.status_code == 403
        assert response["Content-Type"] == "application/problem+json"
        assert _body(response)["status"] == 403
