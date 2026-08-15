"""Structured logging and request correlation.

Every log line is JSON with a stable set of fields and a request id. Without
the id each line is an orphan: interleaved output from concurrent requests
cannot be untangled, and reconstructing one request becomes archaeology
(architecture.md 3.7).

The id is stored in a :class:`~contextvars.ContextVar` rather than
thread-local storage. Django runs under ASGI here (invariant 12), where a
single thread interleaves many requests, and thread-local state would attribute
one request's logs to another.
"""

import json
import logging
import re
import uuid
from contextvars import ContextVar

# Empty rather than None so callers never have to handle two absent cases.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Long enough for a UUID or a cloud provider's trace id, short enough that one
# request cannot turn into megabytes of log.
MAX_REQUEST_ID_LENGTH = 200

# Deliberately narrow. The inbound header is chosen by the caller, and a value
# containing a newline lets that caller forge log entries in any handler that
# is not strictly JSON-encoded. Covers UUIDs, W3C traceparent and the opaque
# ids most proxies generate.
_SAFE_REQUEST_ID = re.compile(rf"\A[A-Za-z0-9._:-]{{1,{MAX_REQUEST_ID_LENGTH}}}\Z")

# What a log line shows when nothing is in flight — startup, a management
# command, a Celery worker.
NO_REQUEST = "-"


def new_request_id() -> str:
    return str(uuid.uuid4())


def sanitise_request_id(candidate: str | None) -> str:
    """Adopt the caller's id when it is safe, otherwise mint one.

    Adopting it is the point: the frontend generates an id, Django reuses it,
    and one query returns both sides of the same request. Validating it is what
    makes that safe to do with attacker-controlled input.
    """
    if candidate and _SAFE_REQUEST_ID.match(candidate):
        return candidate
    return new_request_id()


class RequestIDFilter(logging.Filter):
    """Attach the current request id to every record.

    A filter rather than a formatter concern, so the id is available to any
    handler and formatter, including ones added later.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or NO_REQUEST
        # Always True. This enriches records; it must never suppress one.
        return True


# Attributes the logging module puts on every record. Anything else was passed
# by the caller through `extra=` and is worth emitting.
_STANDARD_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "request_id",
}


class JsonFormatter(logging.Formatter):
    """Render a record as a single JSON object.

    Built with ``json.dumps`` rather than string interpolation because log
    messages contain quotes, backslashes and newlines, and a hand-built line
    would produce output no parser can read — usually at the moment the output
    matters most.

    Anything passed via ``extra=`` becomes a top-level field, which is what
    makes a log line queryable: ``status=500`` is a filter, whereas the same
    number inside a sentence is a substring search.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            # getattr, not record.request_id: a handler configured without the
            # filter must not crash the process it is trying to describe.
            "request_id": getattr(record, "request_id", NO_REQUEST),
        }

        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _STANDARD_RECORD_FIELDS
            }
        )

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str so an unserialisable value in a record degrades to its
        # repr instead of raising inside the logging machinery.
        return json.dumps(payload, default=str)
