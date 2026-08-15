"""Structured logging and request correlation.

Without a correlation ID every log line is an orphan: you cannot reconstruct a
single request from interleaved output, which is exactly what you need at 3am.
architecture.md 3.7 requires the id to propagate Next.js -> Django -> Celery,
and notes that without it debugging is archaeology.

Log records are emitted outside any request too — at startup, from management
commands, from the Celery worker — so nothing here may assume a request exists.
"""

from __future__ import annotations

import json
import logging


def _record(**kwargs) -> logging.LogRecord:
    defaults = {
        "name": "apps.core",
        "level": logging.INFO,
        "pathname": __file__,
        "lineno": 1,
        "msg": "something happened",
        "args": (),
        "exc_info": None,
    }
    return logging.LogRecord(**{**defaults, **kwargs})


class TestRequestIdSanitisation:
    """The inbound header is attacker-controlled.

    A client picks its own X-Request-ID, so the value reaches the log pipeline
    unvalidated unless something stops it. Two concrete risks: an enormous
    value turns one request into megabytes of logs, and control characters
    forge extra lines in any handler that is not strictly JSON.
    """

    def test_a_well_formed_id_is_kept(self) -> None:
        """Honouring the caller's id is the whole point — it is what lets a
        trace span the frontend and the backend."""
        from apps.core.logging import sanitise_request_id

        assert sanitise_request_id("7f3a1c2e-4b5d-6e7f-8a9b-0c1d2e3f4a5b") == (
            "7f3a1c2e-4b5d-6e7f-8a9b-0c1d2e3f4a5b"
        )

    def test_a_missing_id_is_generated(self) -> None:
        from apps.core.logging import sanitise_request_id

        assert sanitise_request_id(None)
        assert sanitise_request_id("")

    def test_two_generated_ids_differ(self) -> None:
        from apps.core.logging import sanitise_request_id

        assert sanitise_request_id(None) != sanitise_request_id(None)

    def test_an_id_with_control_characters_is_replaced(self) -> None:
        """Log forging: a newline lets a caller write its own log lines."""
        from apps.core.logging import sanitise_request_id

        forged = "abc\nERROR fabricated entry"

        assert sanitise_request_id(forged) != forged

    def test_an_oversized_id_is_replaced(self) -> None:
        """One request should not be able to produce megabytes of log."""
        from apps.core.logging import MAX_REQUEST_ID_LENGTH, sanitise_request_id

        oversized = "a" * (MAX_REQUEST_ID_LENGTH + 1)

        assert sanitise_request_id(oversized) != oversized

    def test_an_id_at_the_limit_is_kept(self) -> None:
        from apps.core.logging import MAX_REQUEST_ID_LENGTH, sanitise_request_id

        at_limit = "a" * MAX_REQUEST_ID_LENGTH

        assert sanitise_request_id(at_limit) == at_limit


class TestRequestIdFilter:
    def test_attaches_the_current_request_id(self) -> None:
        from apps.core.logging import RequestIDFilter, request_id_var

        token = request_id_var.set("known-id")
        try:
            record = _record()
            RequestIDFilter().filter(record)

            assert record.request_id == "known-id"
        finally:
            request_id_var.reset(token)

    def test_uses_a_placeholder_outside_a_request(self) -> None:
        """Startup, management commands and Celery all log with no request in
        flight. A missing attribute there would break the formatter."""
        from apps.core.logging import RequestIDFilter

        record = _record()
        RequestIDFilter().filter(record)

        assert record.request_id == "-"

    def test_never_drops_a_record(self) -> None:
        """This filter enriches; it must not be able to suppress logging."""
        from apps.core.logging import RequestIDFilter

        assert RequestIDFilter().filter(_record()) is True


class TestJsonFormatter:
    def test_emits_valid_json(self) -> None:
        from apps.core.logging import JsonFormatter

        parsed = json.loads(JsonFormatter().format(_record()))

        assert parsed["message"] == "something happened"

    def test_carries_the_fields_needed_to_query_logs(self) -> None:
        from apps.core.logging import JsonFormatter, RequestIDFilter, request_id_var

        token = request_id_var.set("trace-me")
        try:
            record = _record()
            RequestIDFilter().filter(record)
            parsed = json.loads(JsonFormatter().format(record))

            assert parsed["level"] == "INFO"
            assert parsed["logger"] == "apps.core"
            assert parsed["request_id"] == "trace-me"
            assert "timestamp" in parsed
        finally:
            request_id_var.reset(token)

    def test_survives_a_record_the_filter_never_touched(self) -> None:
        """A handler configured without the filter must not crash the process
        it is trying to describe."""
        from apps.core.logging import JsonFormatter

        parsed = json.loads(JsonFormatter().format(_record()))

        assert parsed["request_id"] == "-"

    def test_includes_the_traceback_when_there_is_one(self) -> None:
        from apps.core.logging import JsonFormatter

        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _record(level=logging.ERROR, msg="failed", exc_info=sys.exc_info())

        parsed = json.loads(JsonFormatter().format(record))

        assert "ValueError: boom" in parsed["exception"]

    def test_a_message_with_a_quote_does_not_break_the_json(self) -> None:
        """The reason to format JSON with a serialiser rather than an f-string."""
        from apps.core.logging import JsonFormatter

        record = _record(msg='he said "hello" and \\ then left')
        parsed = json.loads(JsonFormatter().format(record))

        assert parsed["message"] == 'he said "hello" and \\ then left'
