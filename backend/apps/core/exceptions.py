"""RFC 9457 Problem Details error responses.

architecture.md 6.1 requires one error shape everywhere, so the frontend has a
single error component instead of a branch per endpoint.

The document carries exactly the members that document specifies — ``type``,
``title``, ``status``, ``detail``, ``errors``. RFC 9457 also defines
``instance``; it is omitted deliberately rather than quietly added, so the
shape stays identical to the one the generated TypeScript is checked against.
Extension members are permitted by the RFC and will be how M4 attaches an
entitlement ``reason`` and ``cta`` to a 403.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# RFC 9457 section 3: a client can tell an error document from a payload
# without inspecting the body.
PROBLEM_CONTENT_TYPE = "application/problem+json"

# RFC 9457 section 4.2.1: with no more specific problem type, `about:blank`
# means the title is simply the status phrase.
DEFAULT_PROBLEM_TYPE = "about:blank"

# ADR-004. Clients branch on the type, not the status code.
#
# Kept deliberately small: a type earns its place only where the status is
# genuinely ambiguous. DRF downgrades NotAuthenticated to 403 whenever no
# authenticator offers a WWW-Authenticate header, and SessionAuthentication
# offers none — so "log in" and "you may not do that" are the same status and
# need telling apart. A 404 or a 429 needs nothing; the status says everything.
#
# These URIs are part of the API contract. Renaming one breaks any client
# branching on it, so they live here and nowhere else. Relative references are
# permitted by RFC 9457 and avoid baking a hostname into the contract.
PROBLEM_TYPES: dict[type[Exception], tuple[str, str]] = {
    exceptions.NotAuthenticated: ("/problems/not-authenticated", "Authentication required"),
    exceptions.AuthenticationFailed: ("/problems/authentication-failed", "Authentication failed"),
    exceptions.PermissionDenied: ("/problems/permission-denied", "Permission denied"),
    # Raised by Django's own decorators; must not look different to a client.
    DjangoPermissionDenied: ("/problems/permission-denied", "Permission denied"),
}


def _classify(exc: Exception, status_code: int) -> tuple[str, str]:
    """Return the ``(type, title)`` pair for an exception.

    An explicit ``problem_type`` on the exception wins, which is the extension
    point M4 uses: ``EntitlementDenied`` declares its own type and adds
    ``reason`` and ``cta`` without this function changing.
    """
    declared = getattr(exc, "problem_type", None)
    if declared:
        return declared, getattr(exc, "problem_title", None) or HTTPStatus(status_code).phrase

    for exc_class, classification in PROBLEM_TYPES.items():
        if isinstance(exc, exc_class):
            return classification

    return DEFAULT_PROBLEM_TYPE, HTTPStatus(status_code).phrase


# DRF's payload for a ValidationError raised without a field name.
NON_FIELD_ERRORS_KEY = "non_field_errors"


def _flatten(value: Any) -> list[str]:
    """Reduce whatever DRF produced to a flat list of plain strings.

    Serializer errors nest arbitrarily — a nested serializer yields a dict, a
    ListField yields a list of dicts. The frontend should never have to walk
    that, and it should never have to test whether a value is a string or a
    list before rendering it.

    ``str()`` also strips ``ErrorDetail``, a str subclass carrying a ``code``
    attribute that otherwise leaks through serialisation and confuses the
    generated TypeScript.
    """
    if isinstance(value, dict):
        return [message for nested in value.values() for message in _flatten(nested)]
    if isinstance(value, list | tuple):
        return [message for item in value for message in _flatten(item)]
    return [str(value)]


def _split(data: Any) -> tuple[str | None, dict[str, list[str]] | None]:
    """Separate DRF's payload into a human-readable detail and a field map."""
    if isinstance(data, dict):
        # The common APIException shape: a single message, no field errors.
        if set(data) == {"detail"}:
            return str(data["detail"]), None
        return None, {field: _flatten(messages) for field, messages in data.items()}

    if isinstance(data, list | tuple):
        # `raise ValidationError([...])` — real errors, but no field to hang
        # them on.
        return None, {NON_FIELD_ERRORS_KEY: _flatten(data)}

    return str(data), None


def problem_details_exception_handler(exc: Exception, context: dict) -> Response | None:
    """Convert DRF exceptions into Problem Details documents.

    Returns ``None`` for anything DRF does not recognise. That is deliberate:
    a non-API exception is a bug rather than a client error, and letting it
    propagate keeps Django's 500 handling — which is what error tracking hooks
    into — intact. Converting it here would buy a tidier response body at the
    cost of losing the report, and the frontend needs a non-JSON fallback
    regardless, since a gateway timeout is never JSON either.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    status_code = response.status_code
    detail, errors = _split(response.data)
    problem_type, title = _classify(exc, status_code)

    if detail is None:
        # Field errors carry the specifics; this is the summary above them.
        detail = getattr(exc, "default_detail", None) or HTTPStatus(status_code).phrase

    document = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": str(detail),
        "errors": errors,
    }

    # RFC 9457 §3.2 extension members. An exception may add its own, which is
    # how an entitlement denial carries `reason` and `cta` without the handler
    # knowing anything about entitlements — core must not import a product app.
    #
    # Standard members win on collision, deliberately: an exception that could
    # overwrite `status` or `type` could make a 403 describe itself as a 200,
    # and clients branch on those (ADR-004).
    for key, value in getattr(exc, "extensions", {}).items():
        document.setdefault(key, value)

    response.data = document
    response.content_type = PROBLEM_CONTENT_TYPE
    return response
