"""A urlconf that routes Django Admin, for tests only.

``config/urls.py`` deliberately does not route ``admin/``: it is the
highest-value target in the system and stays unreachable until M10 hardens it
(obscure path, staff-only, 2FA, audit logging). The review queue still has to
be proven to work, so the suite points ``ROOT_URLCONF`` here instead of
weakening the real one.

Keeping this in ``tests/`` rather than ``config/`` is the point. A module in
``config/`` that routes admin is one settings typo away from being the
production urlconf.
"""

from django.contrib import admin
from django.urls import path

from config.urls import urlpatterns as production_urlpatterns

urlpatterns = [
    *production_urlpatterns,
    path("admin/", admin.site.urls),
]
