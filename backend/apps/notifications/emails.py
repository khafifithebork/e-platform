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

import logging

from django.template.loader import render_to_string

from apps.notifications.services import send_transactional_email

logger = logging.getLogger(__name__)


def _render(name: str, context: dict) -> tuple[str, str]:
    """Render one message's subject and body.

    Both stripped: a template file ends with a newline, and a subject carrying
    one is a malformed header rather than a cosmetic problem.
    """
    subject = render_to_string(f"email/{name}/subject.txt", context).strip()
    body = render_to_string(f"email/{name}/body.txt", context).strip()
    return subject, body


# The two messages whose whole purpose is to reach an address nobody has
# confirmed yet. Everything else is held to abuse case 7.
REACHES_UNVERIFIED = frozenset({"verification", "password_reset"})


def _send(name: str, *, to: str, context: dict) -> None:
    subject, body = _render(name, context)
    send_transactional_email(to=to, subject=subject, body=body)


def _send_to_account(name: str, *, to: str, context: dict) -> bool:
    """Send, but only to an address the account has confirmed. Abuse case 7.

    **Why the exemptions are not a loophole.** A verification email exists to
    reach an unverified address; a password reset has to work for someone who
    never confirmed theirs, or an unverified account becomes unrecoverable
    rather than merely unverified. Both are listed by name, so adding a third
    exemption is a visible edit rather than a forgotten check.

    **What this actually prevents.** An unverified address is one nobody has
    proved they control — it may be a typo for a real person's mailbox, or an
    address someone else owns. Everything outside the two exemptions tells that
    mailbox something about an account: that its password changed, that a
    course was submitted. Sending those to an unproven address hands account
    activity to a stranger, and does it in a way that looks like normal
    behaviour.

    **Skipped, not raised**, and that is a correction of this function's first
    version. Raising made a *notification policy* fail the operation it
    describes: a learner who had never confirmed their address got a 500 when
    changing their password, because the notice about the change refused
    itself. Approving a course would have failed the same way for an
    unverified instructor.

    A notification is secondary to the thing it reports. It may decline to go
    out; it may not take the action down with it. The decline is logged so the
    silence is findable, and `test_discovery_abuse_cases.py` asserts the
    outbox stays empty rather than trusting the log.

    Returns whether it sent, so a caller that genuinely needs to know can ask.
    """
    from apps.accounts.models import User

    if not User.objects.filter(email=to, is_email_verified=True).exists():
        # The address is not logged: it is personal data, and the message name
        # plus the fact of the refusal is the operationally useful half.
        logger.info(
            "email_withheld_unverified_address",
            # `template`, not `message`: `LogRecord` reserves `message` and
            # raises "attempt to overwrite" — a logging call that breaks the
            # request it was added to observe.
            extra={"event": "email_withheld_unverified_address", "template": name},
        )
        return False

    _send(name, to=to, context=context)
    return True


def send_verification_email(*, to: str, token: str) -> None:
    """The token that proves the address is reachable."""
    _send("verification", to=to, context={"token": token})


def send_password_reset_email(*, to: str, token: str) -> None:
    _send("password_reset", to=to, context={"token": token})


def send_password_changed_email(*, to: str) -> bool:
    """A notice, not a confirmation.

    It exists because the person who most needs to know a password changed is
    the one who did not change it. Sent after the change rather than before,
    and it carries no token: a "was this you?" link is a phishing template
    somebody else can copy.
    """
    return _send_to_account("password_changed", to=to, context={})


def send_course_submitted_email(*, to: str, course_title: str, instructor_name: str) -> bool:
    """architecture.md:218 — an instructor submits, a reviewer is told.

    Addressed to one administrator per call. The interface takes a single
    recipient (`OutboundEmail.to`) precisely so a transactional message cannot
    quietly reach a list.
    """
    return _send_to_account(
        "course_submitted",
        to=to,
        context={"course_title": course_title, "instructor_name": instructor_name},
    )


def send_entitlement_drift_alert(*, to: str, findings) -> None:
    """The one operational message in a module of transactional ones.

    **It deliberately does not go through `_send_to_account`.** Every other
    message here is addressed to a person who holds an account, and abuse case
    7 stops those reaching an address nobody has proved they control. This one
    is addressed to whoever `OPERATIONS_ALERT_EMAIL` names — an operator, quite
    possibly not a user of the platform at all. Holding it to the
    verified-account rule would mean the alert silently never sends, which is
    the failure mode an alert exists to prevent.

    The address is configured by the operator rather than supplied by anybody,
    so the threat the rule guards against is not present.

    **Findings are split in the body, not just counted.** M14 §6 case 6 wants
    an alert that names what it found; ADR-002 §4 wants one somebody reads. A
    message saying "5 findings" makes the reader run the command to learn
    whether any of them matter, and one that lumps a lapsed ACTIVE row in with
    a stale CANCELED one trains them to assume it does not.

    **Subscription ids, never email addresses.** The ids come from T3's
    selector, which reads primary keys precisely so this message can carry
    something identifying without carrying personal data into a mailbox nobody
    audits.
    """
    granting_findings = [finding for finding in findings if finding.grants_access]
    stale_findings = [finding for finding in findings if not finding.grants_access]

    _send(
        "entitlement_drift",
        to=to,
        context={
            "granting": len(granting_findings),
            "total": len(findings),
            "granting_findings": granting_findings,
            "stale_findings": stale_findings,
        },
    )


def send_course_reviewed_email(*, to: str, course_title: str, decision: str, notes: str) -> bool:
    """The instructor learns what happened to their submission.

    One template for all three decisions rather than three near-identical
    files: the difference is a sentence, and three files drift into three
    different tones for what is one event.
    """
    return _send_to_account(
        "course_reviewed",
        to=to,
        context={"course_title": course_title, "decision": decision, "notes": notes},
    )


def send_stuck_transcription_alert(*, to: str, report) -> None:
    """The second operational message, and it follows the first's reasoning.

    Like `send_entitlement_drift_alert` it deliberately does not go through
    `_send_to_account`: the recipient is whoever `OPERATIONS_ALERT_EMAIL`
    names, an operator who quite possibly holds no account here, and applying
    the verified-account rule would make the alert silently never send — the
    exact failure an alert exists to prevent.

    **Counts and an age, never a title or an id.** M14 §6 case 6. A transcript
    belongs to a lesson, a lesson to a course, and a course to an instructor,
    so naming one would put a person's unfinished work in a mailbox nobody
    audits. The report dataclass carries only two numbers, which is what makes
    that true of any future template rather than only of this one.
    """
    _send(
        "stuck_transcriptions",
        to=to,
        context={"count": report.count, "oldest_age_days": report.oldest_age_days},
    )
