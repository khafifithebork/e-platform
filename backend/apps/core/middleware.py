"""Request-scoped middleware."""

import logging
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.logging import request_id_var, sanitise_request_id

REQUEST_ID_HEADER = "X-Request-ID"

access_log = logging.getLogger("apps.core.access")


class RequestIDMiddleware:
    """Give every request an id, log the outcome, and return the id to the caller.

    Registered first in MIDDLEWARE. Anything rejected by a later middleware —
    a host validation failure, a CSRF rejection — would otherwise be logged
    with no id, and those are exactly the requests worth investigating.

    Returning the id in the response header is what makes it usable from
    outside: a support ticket can quote the id from a browser network tab and
    one log query finds the request.

    **Why this emits its own access line.**

    Django's ``BaseHandler.get_response`` logs 4xx and 5xx responses *after*
    the entire middleware chain has returned — see ``log_response`` there. By
    that point this middleware's context has been torn down, so those records
    carry no request id. They are also the records you most want correlated.
    Rather than leak the context variable past the request to work around it,
    the outcome is logged here, inside the request's own context, where the
    correlation is real. Django's own line remains for its extra detail on
    5xx; it is simply not the one to correlate by.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = sanitise_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = request_id_var.set(request_id)

        # Also on the request, so views and services can read it without
        # importing the context variable.
        request.request_id = request_id

        started = time.monotonic()
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id

            access_log.info(
                "request_finished",
                extra={
                    "event": "request_finished",
                    "method": request.method,
                    # request.path, never the full URL with its query string:
                    # query parameters carry tokens and search terms, and this
                    # line goes to a log aggregator.
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            return response
        finally:
            # Reset even when the view raises. Without this the id outlives the
            # request and attributes later log lines — from a different user,
            # or from no user at all — to this one. A stale id is worse than no
            # id, because it correlates confidently and wrongly.
            request_id_var.reset(token)
