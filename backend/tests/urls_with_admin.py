"""A urlconf that routes Django Admin at a fixed path, for tests only.

M10 routes the real admin site, but only when `DJANGO_ADMIN_PATH` is set, and
the path is deliberately not a constant anything can rely on. Tests that need
to *reach* an admin page — the review queue, the dead-letter queue — point
`ROOT_URLCONF` here and get a stable `/admin/` instead of reaching into
settings.

Tests about the routing itself do not use this: `test_admin_site_routing.py`
reloads the real urlconf, because the conditional is the thing under test.

Keeping this in `tests/` rather than `config/` remains the point. A module in
`config/` that routes admin unconditionally is one settings typo away from
being the production urlconf.
"""

from django.contrib import admin
from django.urls import path

from config.urls import urlpatterns as production_urlpatterns

urlpatterns = [
    *production_urlpatterns,
    path("admin/", admin.site.urls),
]
