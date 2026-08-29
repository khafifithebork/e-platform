"""Error reporting, and the single place the vendor SDK is named.

**Why this is not an adapter.** Invariant 4 puts every external provider behind
an adapter in ``<app>/providers/``, and Sentry is deliberately not one. An
adapter exists so a vendor can be swapped at a call site; Sentry has no call
site. It installs itself into the interpreter at boot — into Django's
middleware stack, Celery's signals and the logging module — and our code never
invokes it. A ``providers/sentry.py`` wrapping a function that runs once would
be an abstraction over nothing.

What invariant 4 is *for* still holds: the vendor's name appears in exactly one
module, and ``test_the_vendor_sdk_is_imported_in_exactly_one_module`` fails if
that stops being true. ADR-027 §1 records the reading.

**Nothing initialises without a DSN.** A DSN is a deployment fact and the
repository does not have one, so a missing variable is the normal case on every
developer machine and in CI. Raising there would make ``manage.py check`` fail
for everyone to protect a production concern; returning False is the honest
answer, and it is asserted rather than assumed.

**What this cannot claim.** No event from this module has ever reached Sentry,
because no DSN exists to send one to. Everything below is configuration and
refusal — both testable — and neither is delivery. ADR-006's inert control, and
it stays inert until somebody provisions the account (M14 T5, "the honest
limit").
"""

from __future__ import annotations

import re
from typing import Any

import sentry_sdk
from sentry_sdk.types import Event, Hint

from apps.core.logging import request_id_var

REDACTED = "[redacted]"

# Deliberately loose on the local part and strict about the shape, because this
# runs over exception messages rather than over a form field: the cost of
# redacting one non-address is a slightly less readable stack trace, and the
# cost of missing a real one is a learner's email address sitting in a
# third-party dashboard nobody audits.
_EMAIL = re.compile(
    r"[^\s<>@,;:\"'()\[\]]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}"
)

# Sentry's own event scrubber caps its work at a similar depth. A cycle cannot
# occur — an event is JSON-serialisable by the time it reaches `before_send` —
# but a RecursionError raised in here would drop the event silently, which is
# the one failure mode an error reporter must not have.
_MAX_DEPTH = 10


def redact_addresses(value: Any, *, depth: int = 0) -> Any:
    """Replace anything shaped like an email address, anywhere in the event.

    This complements the SDK's scrubber rather than repeating it. That one is
    **key**-based — it removes values under names like ``password`` and
    ``authorization`` — and ``email`` is not in its denylist. More to the
    point, a key-based scrubber cannot reach an address embedded in an
    exception *message*, which is exactly the shape this codebase produces:
    account and notification errors quote the address they were given.
    """
    if depth > _MAX_DEPTH:
        return value
    if isinstance(value, str):
        return _EMAIL.sub(REDACTED, value)
    if isinstance(value, dict):
        return {key: redact_addresses(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_addresses(item, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_addresses(item, depth=depth + 1) for item in value)
    return value


def _before_send(event: Event, hint: Hint) -> Event | None:
    """Scrub, then correlate.

    The ``request_id`` tag is what makes this milestone's two halves meet: M14
    T2 propagates the id from the browser through Django into Celery, and
    without it here a Sentry issue and the log lines describing the same
    request can only be joined by timestamp.
    """
    scrubbed: Event = redact_addresses(event)

    # Scrub first so the tag cannot be mangled by it, and read the contextvar
    # rather than the event: a task picks the id up from its message header,
    # where no request exists to carry one.
    request_id = request_id_var.get()
    if request_id:
        tags = dict(scrubbed.get("tags") or {})
        tags["request_id"] = request_id
        scrubbed["tags"] = tags

    return scrubbed


def initialise_error_reporting(
    *,
    dsn: str,
    environment: str,
    traces_sample_rate: float = 0.0,
    release: str = "",
) -> bool:
    """Configure Sentry. Returns whether it was configured.

    Django and Celery integrations are **auto-enabled** from the installed
    packages, so neither is passed explicitly — and one ``init`` in settings
    covers the worker too, because Django sets up in that process as well.
    """
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        # Explicit, though the SDK currently treats None the same way. A
        # default is a fact about a version; this is a line a reviewer can see
        # and a test can assert. With it off, Django user objects and request
        # bodies and headers are never attached.
        send_default_pii=False,
        # Tracing bills a separate quota from errors, and the free tier's is
        # small enough that turning it on by accident is how a month's budget
        # disappears before anybody looks. Whether we want traces at all is
        # M14 T6's question; T5 ships errors.
        traces_sample_rate=traces_sample_rate,
        before_send=_before_send,
    )
    return True
