"""The email provider interface.

Invariant 4: every external provider sits behind an adapter. The vocabulary
here is **ours** — a subject, a recipient, a plain-text body — because the
payment, video and transcription interfaces all learned the same lesson: an
interface shaped like one vendor's payload is an interface that has to be
rewritten when the vendor changes.

**What this deliberately does not model:** attachments, templates rendered by
the provider, scheduled sends, tags, batch endpoints, or a webhook for delivery
events. Every one of those is a real Resend feature and none of them has been
verified against a document — §6 forbids inventing provider capabilities, and
the cheapest place to invent one is an interface nobody has implemented yet.
They arrive when the provider does, shaped by what it actually offers.

An adapter never touches the ORM. It takes and returns plain data; the service
layer decides what that means for our database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

NEWLINES = ("\n", "\r")


class EmailNotSent(Exception):
    """The provider did not accept the message.

    Distinct from "the provider accepted it and the mailbox bounced later",
    which this interface cannot observe and does not pretend to. Raising is what
    lets the task retry; a bounce is a webhook and arrives with a provider.
    """


@dataclass(frozen=True)
class OutboundEmail:
    """One message, as this codebase describes it.

    Frozen: a message that a provider has been handed must not change
    underneath a retry.

    `to` is a single address rather than a list. Every email this product sends
    is addressed to one person, and a list invites the bug where a transactional
    message reaches somebody it was not about.
    """

    to: str
    subject: str
    body: str

    def __post_init__(self) -> None:
        """Refuse a subject that could forge a header.

        Checked when the message is built rather than left to the backend,
        because the backend raises at *send* time — which is inside a retrying
        Celery task. One injected newline would become four SMTP attempts and
        four tracebacks for an error that can never succeed. A malformed
        message is not a transient failure and must not be queued as one.

        The body is not checked: nothing parses it, and a newline in it is
        simply a newline.
        """
        if any(character in self.subject for character in NEWLINES):
            raise ValueError("An email subject may not contain a newline.")


@runtime_checkable
class EmailProvider(Protocol):
    """What any email provider must be able to do for us.

    One method. It is the whole of what M11 needs, and a speculative surface
    is how an interface stops being replaceable.
    """

    name: str

    def send(self, message: OutboundEmail) -> str:
        """Hand one message over. Returns the provider's id for it, if any.

        Raises `EmailNotSent` if the provider refused it. The return value is
        recorded nowhere yet (ADR-020 §8) and exists so that the day there is
        something to record, the adapter is not the thing that has to change.
        """
        ...
