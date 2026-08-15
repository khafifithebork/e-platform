"""Request correlation, end to end through the middleware.

The unit tests cover sanitisation and formatting. These prove the middleware is
installed and that the id reaches the client, which is what lets a browser
network tab and a log query be joined up.
"""

from __future__ import annotations

HEADER = "X-Request-ID"


class TestResponseCarriesTheId:
    def test_every_response_has_one(self, client) -> None:
        response = client.get("/healthz")

        assert response.headers[HEADER]

    def test_two_requests_get_different_ids(self, client) -> None:
        first = client.get("/healthz").headers[HEADER]
        second = client.get("/healthz").headers[HEADER]

        assert first != second


class TestInboundIdIsHonoured:
    def test_a_caller_supplied_id_is_echoed(self, client) -> None:
        """This is what makes a trace span services: Next.js generates the id,
        Django adopts it, and one query finds both sides of the request."""
        response = client.get("/healthz", headers={HEADER: "from-the-frontend"})

        assert response.headers[HEADER] == "from-the-frontend"

    def test_a_forged_id_is_not_echoed(self, client) -> None:
        """The header is attacker-controlled. A value containing a newline
        would let a caller write its own log lines."""
        forged = "abc\nERROR fabricated entry"

        response = client.get("/healthz", headers={HEADER: forged})

        assert response.headers[HEADER] != forged
        assert "\n" not in response.headers[HEADER]


class TestTheIdReachesLogRecords:
    """The actual point of the exercise.

    Echoing a header is worthless on its own — the id has to appear on the log
    lines the request produces, or you still cannot reconstruct it. This is
    asserted through a real request rather than by setting the context variable
    by hand, because the interesting failure is the id not propagating to
    wherever the logging happens.
    """

    def test_the_access_line_carries_the_id(self, client, caplog) -> None:
        import logging

        with caplog.at_level(logging.INFO, logger="apps.core.access"):
            client.get("/healthz", headers={HEADER: "correlate-me"})

        lines = [r for r in caplog.records if r.name == "apps.core.access"]

        assert lines, "expected an access log line"
        assert all(record.request_id == "correlate-me" for record in lines)

    def test_the_access_line_is_queryable(self, client, caplog) -> None:
        """Fields, not prose. `status=404` is a filter; the same number inside
        a sentence is a substring search."""
        import logging

        with caplog.at_level(logging.INFO, logger="apps.core.access"):
            client.get("/no-such-route")

        line = next(r for r in caplog.records if r.name == "apps.core.access")

        assert line.event == "request_finished"
        assert line.method == "GET"
        assert line.path == "/no-such-route"
        assert line.status == 404
        assert isinstance(line.duration_ms, float)

    def test_the_access_line_omits_the_query_string(self, client, caplog) -> None:
        """Query parameters carry tokens and search terms, and this line goes
        to a log aggregator."""
        import logging

        with caplog.at_level(logging.INFO, logger="apps.core.access"):
            client.get("/healthz?token=secret-value")

        line = next(r for r in caplog.records if r.name == "apps.core.access")

        assert line.path == "/healthz"
        assert "secret-value" not in line.getMessage()

    def test_a_log_line_outside_a_request_still_has_the_field(self, caplog) -> None:
        """Startup and Celery log with no request in flight. The field must
        exist regardless, or the formatter has to special-case it."""
        import logging

        with caplog.at_level(logging.WARNING, logger="apps.core"):
            logging.getLogger("apps.core").warning("no request here")

        assert caplog.records[0].request_id == "-"


class TestMiddlewareIsInstalled:
    def test_registered_first(self, settings) -> None:
        """It must run before everything else, or requests rejected by an
        earlier middleware are logged with no id — and those are precisely the
        ones worth investigating."""
        assert settings.MIDDLEWARE[0] == "apps.core.middleware.RequestIDMiddleware"

    def test_the_id_does_not_leak_between_requests(self, client) -> None:
        """The context variable must be reset. A leaked id would attribute one
        user's log lines to another user's request."""
        from apps.core.logging import request_id_var

        client.get("/healthz")

        assert request_id_var.get() == ""
