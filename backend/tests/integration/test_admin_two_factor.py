"""Two-factor authentication on the admin site. Abuse case 2.

T5 routed the admin and left `is_staff` as the only real gate. This is the
control that makes routing it defensible: a password alone protects a surface
that can grant free access and issue refunds, and passwords are phished.

The test that carries the milestone is
`test_staff_without_a_device_are_refused` — a correct password and `is_staff`
must not be enough.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import clear_url_caches
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Role

PASSWORD = "a-long-enough-passphrase"
ADMIN_PATH = "staff-console-test"

# A needle that appears on the dashboard and *not* on the login page.
#
# The first version of this file looked for "Site administration", which this
# site renames — so it appeared nowhere, and every "not in" assertion below
# passed against any response at all. `test_the_marker_discriminates` is what
# stops that recurring.
DASHBOARD = b"Operations"

pytestmark = pytest.mark.django_db


@pytest.fixture
def routed(settings):
    import importlib

    from config import urls as url_conf

    settings.ADMIN_PATH = ADMIN_PATH
    importlib.reload(url_conf)
    clear_url_caches()
    yield ADMIN_PATH

    settings.ADMIN_PATH = ""
    importlib.reload(url_conf)
    clear_url_caches()


def _staff(email: str = "staff@example.test", *, staff: bool = True):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    user.role = Role.ADMIN
    user.is_staff = staff
    user.save(update_fields=["role", "is_staff"])
    return user


def _verify(client, device) -> None:
    """Mark this session as having passed the second factor.

    What `django_otp.login` does, without needing a request object: the
    middleware reads this key and it is what makes `is_verified()` true.
    """
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()


class TestAPasswordIsNotEnough:
    def test_staff_without_a_device_are_refused(self, client, routed) -> None:
        """The milestone's control, in one test.

        Correct password, `is_staff` true, and still no admin site. Before
        T6 this exact request returned the dashboard.
        """
        client.force_login(_staff())

        response = client.get(f"/{routed}/", follow=True)

        assert DASHBOARD not in response.content
        assert b"password" in response.content.lower()

    def test_a_device_alone_is_not_enough_either(self, client, routed) -> None:
        """Having enrolled is not the same as having verified this session.
        Otherwise a stolen session cookie would walk straight in."""
        user = _staff()
        TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        client.force_login(user)

        response = client.get(f"/{routed}/", follow=True)

        assert DASHBOARD not in response.content

    def test_a_verified_session_gets_in(self, client, routed) -> None:
        """The positive twin, and it is doing real work: an admin site that
        refused everybody would satisfy both tests above and look identical."""
        user = _staff()
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        client.force_login(user)
        _verify(client, device)

        response = client.get(f"/{routed}/")

        assert response.status_code == 200
        assert DASHBOARD in response.content

    def test_an_unconfirmed_device_is_never_offered_at_login(self) -> None:
        """A half-finished enrolment grants nothing — but not where I first
        looked, and the correction is the point.

        This originally planted an unconfirmed device's id directly in the
        session and expected refusal. It got in: django-otp's
        `Device.from_persistent_id` does **not** filter on `confirmed`, so a
        session already naming a device verifies regardless. The flag is
        honoured one step earlier, in `devices_for_user`, which is what the
        login form challenges against — so an unconfirmed device can never get
        its id into a session through any real flow.

        Asserting the stronger claim would have documented behaviour
        django-otp does not have. This asserts the true one.
        """
        from django_otp import devices_for_user

        user = _staff()
        TOTPDevice.objects.create(user=user, name="half-enrolled", confirmed=False)

        assert list(devices_for_user(user)) == []

    def test_but_a_confirmed_one_is(self) -> None:
        """The twin. `devices_for_user` returning nothing for everybody would
        satisfy the test above and lock out the world."""
        from django_otp import devices_for_user

        user = _staff()
        TOTPDevice.objects.create(user=user, name="default", confirmed=True)

        assert [device.name for device in devices_for_user(user)] == ["default"]


class TestTheMarkerDiscriminates:
    def test_the_dashboard_carries_it_and_the_login_page_does_not(self, client, routed) -> None:
        """The twin for every negative assertion in this file. A needle that
        matches nothing makes "not in" vacuously true, which is how the first
        version of these tests passed while proving nothing.
        """
        user = _staff()
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        client.force_login(user)

        before = client.get(f"/{routed}/", follow=True).content
        _verify(client, device)
        after = client.get(f"/{routed}/").content

        assert DASHBOARD not in before
        assert DASHBOARD in after


class TestTheSiteIsTheHardenedOne:
    def test_the_admin_site_requires_verification(self) -> None:
        """Structural, because the behavioural tests above would also pass if
        the site were refusing everyone for an unrelated reason."""
        from django.contrib import admin
        from django_otp.admin import OTPAdminSite

        assert isinstance(admin.site, OTPAdminSite)

    def test_it_keeps_the_admin_url_namespace(self) -> None:
        """`OTPAdminSite` defaults its name to `otpadmin`, which renames every
        reversed URL and breaks links inside pages this codebase registers."""
        from django.contrib import admin

        assert admin.site.name == "admin"

    def test_the_middleware_runs_after_authentication(self, settings) -> None:
        """Order is the control. Before `AuthenticationMiddleware` there is no
        user to verify, and `is_verified()` would not exist for the admin site
        to consult."""
        order = settings.MIDDLEWARE

        assert order.index("django_otp.middleware.OTPMiddleware") > order.index(
            "django.contrib.auth.middleware.AuthenticationMiddleware"
        )

    def test_only_totp_is_enabled(self, settings) -> None:
        """Static tokens are a recovery mechanism with no process behind it
        yet, and an unused recovery path is a second way in."""
        otp_apps = [app for app in settings.INSTALLED_APPS if app.startswith("django_otp")]

        assert otp_apps == ["django_otp", "django_otp.plugins.otp_totp"]


class TestEnrolment:
    """The bootstrap problem: the admin site is where devices are managed, and
    it cannot be reached without a device."""

    def test_it_creates_a_confirmed_device(self) -> None:
        user = _staff()

        call_command("enrol_admin_totp", "staff@example.test", verbosity=0)

        device = TOTPDevice.objects.get(user=user)
        assert device.confirmed is True
        assert device.config_url.startswith("otpauth://totp/")

    def test_it_refuses_a_non_staff_account(self) -> None:
        """A device on an account that cannot use the admin grants nothing and
        suggests otherwise."""
        _staff("learner@example.test", staff=False)

        with pytest.raises(CommandError, match="not staff"):
            call_command("enrol_admin_totp", "learner@example.test", verbosity=0)

        assert not TOTPDevice.objects.exists()

    def test_it_refuses_an_unknown_account(self) -> None:
        with pytest.raises(CommandError, match="No account"):
            call_command("enrol_admin_totp", "nobody@example.test", verbosity=0)

    def test_it_will_not_silently_replace_a_device(self) -> None:
        """Re-running by accident would lock the holder out of their own
        authenticator with no warning."""
        user = _staff()
        call_command("enrol_admin_totp", "staff@example.test", verbosity=0)
        first = TOTPDevice.objects.get(user=user).key

        with pytest.raises(CommandError, match="already has a device"):
            call_command("enrol_admin_totp", "staff@example.test", verbosity=0)

        assert TOTPDevice.objects.get(user=user).key == first

    def test_but_replace_says_so_explicitly(self) -> None:
        user = _staff()
        call_command("enrol_admin_totp", "staff@example.test", verbosity=0)
        first = TOTPDevice.objects.get(user=user).key

        call_command("enrol_admin_totp", "staff@example.test", "--replace", verbosity=0)

        assert TOTPDevice.objects.filter(user=user).count() == 1
        assert TOTPDevice.objects.get(user=user).key != first

    def test_the_device_it_makes_actually_verifies(self, client, routed) -> None:
        """End to end: enrol through the command, then reach the admin with
        the device it created. Without this the command could be producing
        devices that do not work."""
        user = _staff()
        call_command("enrol_admin_totp", "staff@example.test", verbosity=0)
        client.force_login(user)
        _verify(client, TOTPDevice.objects.get(user=user))

        assert client.get(f"/{routed}/").status_code == 200
