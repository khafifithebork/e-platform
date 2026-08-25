"""The admin AppConfig, alone in its own module.

Separate from `apps.py` for a mechanical reason worth recording: Django scans
a module for `AppConfig` subclasses to decide which is the default, and the
imported `AdminConfig` this one inherits from counts as a second candidate.
Putting both here would break startup with "declares more than one default
AppConfig", which is a confusing error to meet later.
"""

from django.contrib.admin.apps import AdminConfig


class HardenedAdminConfig(AdminConfig):
    """Replaces `django.contrib.admin` in INSTALLED_APPS.

    The one supported place to say "use a different AdminSite". Listing this
    instead of `django.contrib.admin` is what makes 2FA unavoidable rather than
    something each `ModelAdmin` has to remember.
    """

    default_site = "apps.core.admin_site.HardenedAdminSite"
