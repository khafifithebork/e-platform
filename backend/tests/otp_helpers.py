"""Passing the admin site's second factor, in tests.

T6 put `OTPAdminSite` behind every admin page, which means every existing test
that drives the Django admin — the M3 review queue, the M5 dead-letter queue,
the M4 entitlement admin — now has to verify a session as well as sign in.
That is the control working, not a regression, and this is the one place that
knows how to satisfy it.

Shared rather than copied into each file so that the *next* admin test has an
obvious thing to call, and so a change to how verification works is one edit.
"""

from __future__ import annotations

from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice


def verify_admin_session(client, email: str) -> None:
    """Give this client a confirmed device and mark the session as verified.

    Equivalent to `django_otp.login`, without needing a request object. Only
    meaningful for staff accounts — a device on anything else grants nothing,
    which is what the enrolment command refuses to create.
    """
    from apps.accounts.models import User

    user = User.objects.get(email=email)
    device, _ = TOTPDevice.objects.get_or_create(
        user=user, name="test", defaults={"confirmed": True}
    )

    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
