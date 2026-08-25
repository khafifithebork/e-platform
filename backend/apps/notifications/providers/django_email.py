"""The adapter over Django's own email framework.

**Not a stub, and not a fake.** It sends real SMTP: Mailpit locally, and
whatever `EMAIL_*` points at elsewhere. This is the same trade M5 made with
MinIO — real code exercised against a local server, so what ships is the code
that will run in production with different environment variables.

Resend is not integrated (ADR-020 §7). When it is, it is a sibling of this
file, and nothing above `providers/` changes. Resend offers SMTP as well as an
HTTP API, so this adapter may turn out to be the production path too — which
would make the swap a configuration change rather than a code one.
"""

from __future__ import annotations

from django.core.mail import send_mail

from apps.notifications.providers.base import EmailNotSent, OutboundEmail


class DjangoEmailProvider:
    """Django's `send_mail`, behind the interface.

    `fail_silently=False` deliberately: a provider that swallows its own
    failures makes the task above it believe every send worked, and a retry
    that never fires is worse than no retry.
    """

    name = "django"

    def send(self, message: OutboundEmail) -> str:
        try:
            delivered = send_mail(
                subject=message.subject,
                message=message.body,
                # `None` means `DEFAULT_FROM_EMAIL`. Kept as the single place
                # the sender is configured rather than repeated per call site.
                from_email=None,
                recipient_list=[message.to],
                fail_silently=False,
            )
        except Exception as exc:
            raise EmailNotSent(str(exc)) from exc

        if not delivered:
            # `send_mail` returns the number accepted. Zero without an
            # exception is a backend that declined quietly, and treating it as
            # success is how a verification email is never sent and never
            # reported.
            raise EmailNotSent("The email backend accepted nothing.")

        return ""


def email_provider() -> DjangoEmailProvider:
    """The provider this deployment uses.

    A function rather than a module-level instance, so tests can patch one
    place and so a future provider can be chosen from settings without every
    caller learning about it.
    """
    return DjangoEmailProvider()
