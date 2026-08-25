"""The transactional set. One function per message, one template per message.

**Plain text, and that is a decision rather than a stage.** No HTML email
exists here, so there is nothing to escape and no rendering difference between
clients to test. When HTML arrives it arrives with a provider and a design, and
`test_no_html_template_has_appeared` is what stops it arriving quietly — the
moment it does, autoescaping becomes a real control and this docstring is
wrong.

**Autoescaping is off**, and that is the correct setting for text rather than a
relaxation. Django autoescapes by default whatever the file extension, so an
instructor called `O'Brien` would be greeted as `O&#x27;Brien` in a plain-text
message. There is no injection vector in a body nothing parses as markup.

**The subject is a separate template from the body**, and both are stripped.
A subject is a mail header: a newline in one is header injection, and Django's
`BadHeaderError` is the backstop rather than the plan. Rendering the subject
from its own single-line template keeps user-supplied values in the body, where
a newline is just a newline.

Which messages are here is derived from events this codebase already has, not
from a list in a document — architecture.md names only "the full transactional
email set" and, at line 218, the review notification. Subscription, dunning and
trial mail are deliberately absent: M8 and M9 own those events, and writing
them now would be guessing at semantics that are not decided.
"""

from __future__ import annotations

from django.template.loader import render_to_string

from apps.notifications.services import send_transactional_email


def _render(name: str, context: dict) -> tuple[str, str]:
    """Render one message's subject and body.

    Both stripped: a template file ends with a newline, and a subject carrying
    one is a malformed header rather than a cosmetic problem.
    """
    subject = render_to_string(f"email/{name}/subject.txt", context).strip()
    body = render_to_string(f"email/{name}/body.txt", context).strip()
    return subject, body


def _send(name: str, *, to: str, context: dict) -> None:
    subject, body = _render(name, context)
    send_transactional_email(to=to, subject=subject, body=body)


def send_verification_email(*, to: str, token: str) -> None:
    """The token that proves the address is reachable."""
    _send("verification", to=to, context={"token": token})


def send_password_reset_email(*, to: str, token: str) -> None:
    _send("password_reset", to=to, context={"token": token})


def send_password_changed_email(*, to: str) -> None:
    """A notice, not a confirmation.

    It exists because the person who most needs to know a password changed is
    the one who did not change it. Sent after the change rather than before,
    and it carries no token: a "was this you?" link is a phishing template
    somebody else can copy.
    """
    _send("password_changed", to=to, context={})


def send_course_submitted_email(*, to: str, course_title: str, instructor_name: str) -> None:
    """architecture.md:218 — an instructor submits, a reviewer is told.

    Addressed to one administrator per call. The interface takes a single
    recipient (`OutboundEmail.to`) precisely so a transactional message cannot
    quietly reach a list.
    """
    _send(
        "course_submitted",
        to=to,
        context={"course_title": course_title, "instructor_name": instructor_name},
    )


def send_course_reviewed_email(*, to: str, course_title: str, decision: str, notes: str) -> None:
    """The instructor learns what happened to their submission.

    One template for all three decisions rather than three near-identical
    files: the difference is a sentence, and three files drift into three
    different tones for what is one event.
    """
    _send(
        "course_reviewed",
        to=to,
        context={"course_title": course_title, "decision": decision, "notes": notes},
    )
