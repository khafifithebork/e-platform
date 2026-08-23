"""System checks that catch a misconfiguration before it is a deployment.

`manage.py check --deploy` runs these, which is where a mistake in the admin
path should surface — not in a scanner's logs three weeks later.
"""

from django.conf import settings
from django.core.checks import Error, register

#: Paths a scanner tries first. Not exhaustive, and not meant to be: it exists
#: to catch the specific mistake of setting the variable to the thing §8 says
#: is unacceptable, which is the likeliest way this gets configured wrong.
GUESSABLE_ADMIN_PATHS = frozenset(
    {"admin", "django-admin", "django_admin", "administrator", "backend", "manage", "dashboard"}
)


@register()
def check_admin_path(app_configs, **kwargs):
    """The admin path must not be one of the obvious ones.

    An Error rather than a Warning: §8 calls the default unacceptable for a
    system that can grant free access and issue refunds, and a warning is a
    thing people scroll past.

    Length is deliberately not checked. Any threshold would be invented, and a
    short path chosen deliberately is not the failure this is looking for.
    """
    path = getattr(settings, "ADMIN_PATH", "")
    if path and path.lower() in GUESSABLE_ADMIN_PATHS:
        return [
            Error(
                f"DJANGO_ADMIN_PATH is {path!r}, which is one of the first things "
                "an automated scanner tries.",
                hint=(
                    "Choose something unguessable. Unset the variable to leave the admin unrouted."
                ),
                id="core.E001",
            )
        ]
    return []
