"""Telling django-axes who is being attacked.

By default axes reads the username from ``request.POST[AXES_USERNAME_FORM_FIELD]``,
which is correct for a Django form and empty for a JSON API — ``request.POST``
is only populated for form-encoded bodies.

The failure mode is quiet and complete. Axes still records every failed attempt,
so the table fills up and the logs look right, but each row is stored with
``username=None``. The lockout is keyed on ``(username, ip_address)``, so the
lookup for a real address matches nothing and **the account is never locked**.
Everything appears configured and nothing is protected.
"""

from django.http import HttpRequest


def get_username(request: HttpRequest, credentials: dict | None = None) -> str:
    """Resolve the username being authenticated.

    ``credentials`` is what was passed to ``authenticate()`` and is the
    authoritative source: it is the value actually being checked, rather than a
    re-read of the request body that a middleware might have altered.

    The form-field fallback keeps Django Admin's login working, which does post
    a form.
    """
    if credentials:
        username = credentials.get("username") or credentials.get("email")
        if username:
            return username

    return request.POST.get("email", "")
