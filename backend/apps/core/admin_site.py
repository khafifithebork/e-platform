"""The admin site, with two-factor authentication required.

architecture.md §8: *"mandatory 2FA (`django-otp`)"*. T5 routed the admin at an
unguessable path and left `is_staff` as the only real gate; this is the control
that makes routing it defensible. A password alone protects a surface that can
grant free access and issue refunds, and passwords are phished.

Installed through `AdminConfig.default_site` rather than by reassigning
`admin.site.__class__`. The monkey-patch is widely published and works, but
`admin.site` is a `LazyObject` wrapper, so it is a patch on a proxy — and every
existing `@admin.register` in this codebase would still be pointing at whatever
got constructed first. The app-config hook is the supported seam and needs no
re-registration.
"""

from django_otp.admin import OTPAdminSite


class HardenedAdminSite(OTPAdminSite):
    """`OTPAdminSite`, keeping the `admin` URL namespace.

    `OTPAdminSite` defaults its name to `otpadmin`, which would rename every
    reversed URL — `admin:index` becomes `otpadmin:index` — and quietly break
    the links inside pages this codebase already registers. The name is pinned
    back to `admin` so that nothing else has to know 2FA was added.

    `has_permission` comes from the parent and is the whole control: the
    default staff checks **and** `request.user.is_verified()`, which is false
    until `OTPMiddleware` has matched a confirmed device against the session.
    """

    site_header = "Lingua administration"
    site_title = "Lingua administration"
    index_title = "Operations"

    def __init__(self, name: str = "admin") -> None:
        super().__init__(name)
