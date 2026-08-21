"""Rate limits on the auth endpoints.

`architecture.md` §6.4 sets these numbers, and until now nothing asserted they
do anything. A throttle that is configured but never fires is the same class of
problem as the lockout in T5: it looks protective and is not.

These tests deliberately use the real rates rather than the raised ones the
other suites install, so they are the only place where a 429 is genuinely
provoked.
"""

from __future__ import annotations

import pytest

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
RESET = "/api/v1/auth/password/reset/"
RESEND = "/api/v1/auth/resend-verification/"

PASSWORD = "a-sufficiently-long-passphrase"


def _post(client, path: str, body: dict):
    return client.post(path, body, content_type="application/json")


class TestConfiguredRates:
    """The numbers from §6.4, pinned.

    Config assertions, and they earn it: a rate is a security control, and
    silently loosening one is the sort of change that looks like tuning.
    """

    def test_the_documented_rates(self, settings) -> None:
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

        assert rates["anon"] == "60/min"
        assert rates["user"] == "300/min"
        assert rates["login"] == "10/hour"
        assert rates["register"] == "5/hour"
        assert rates["password_reset"] == "5/hour"
        assert rates["resend_verification"] == "3/hour"
        assert rates["media_upload"] == "30/hour"
        assert rates["progress"] == "40/min"

    def test_auth_endpoints_are_tighter_than_the_anonymous_baseline(self, settings) -> None:
        """Each of these either creates state, sends an email, or is worth
        guessing at. None should sit at the general 60/min."""
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

        for scope in ("login", "register", "password_reset", "resend_verification"):
            count, period = rates[scope].split("/")
            assert period == "hour"
            assert int(count) <= 10


class TestEveryAuthViewDeclaresAScope:
    """A new endpoint that forgets a scope silently inherits the generous
    anonymous limit. This fails the build instead."""

    def test_no_auth_view_is_left_on_the_default(self) -> None:
        from apps.accounts import views

        exempt = {
            # Idempotent, grants nothing, and throttling it would strand a
            # client retrying after a timeout.
            "LogoutView",
        }

        view_classes = [
            attribute
            for name, attribute in vars(views).items()
            if name.endswith("View")
            and hasattr(attribute, "as_view")
            and name not in exempt
            # Defined here, not imported. Otherwise DRF's own APIView is
            # picked up from the module namespace and fails for being generic.
            and getattr(attribute, "__module__", None) == views.__name__
        ]

        assert view_classes, "expected to find auth views"
        for view in view_classes:
            assert getattr(view, "throttle_scope", None), f"{view.__name__} has no throttle_scope"


@pytest.mark.django_db
class TestThrottlesActuallyFire:
    def test_registration_stops_after_its_limit(self, client, settings) -> None:
        limit = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["register"].split("/")[0])

        statuses = [
            _post(
                client, REGISTER, {"email": f"user{index}@example.test", "password": PASSWORD}
            ).status_code
            for index in range(limit + 1)
        ]

        assert statuses[-1] == 429
        assert statuses[:limit] == [202] * limit

    def test_password_reset_stops_after_its_limit(self, client, settings) -> None:
        """Mail-bombing as much as enumeration: this endpoint sends an email to
        whatever address it is given."""
        limit = int(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["password_reset"].split("/")[0]
        )

        for _ in range(limit):
            _post(client, RESET, {"email": "someone@example.test"})

        assert _post(client, RESET, {"email": "someone@example.test"}).status_code == 429

    def test_resend_verification_stops_after_its_limit(self, client, settings) -> None:
        limit = int(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["resend_verification"].split("/")[0]
        )

        for _ in range(limit):
            _post(client, RESEND, {"email": "someone@example.test"})

        assert _post(client, RESEND, {"email": "someone@example.test"}).status_code == 429


@pytest.mark.django_db
class TestScopesAreIndependent:
    def test_exhausting_registration_does_not_block_login(self, client, settings) -> None:
        """Otherwise an attacker could lock every legitimate user out of
        signing in simply by hammering the registration endpoint."""
        limit = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["register"].split("/")[0])

        for index in range(limit + 1):
            _post(client, REGISTER, {"email": f"user{index}@example.test", "password": PASSWORD})

        login = _post(client, LOGIN, {"email": "someone@example.test", "password": PASSWORD})

        assert login.status_code != 429


@pytest.mark.django_db
class TestThrottledResponseShape:
    def _exhaust_resend(self, client, settings):
        limit = int(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["resend_verification"].split("/")[0]
        )
        for _ in range(limit + 1):
            response = _post(client, RESEND, {"email": "someone@example.test"})
        return response

    def test_carries_retry_after(self, client, settings) -> None:
        """architecture.md §6.3 requires it, and without it a client has no
        way to back off other than guessing."""
        response = self._exhaust_resend(client, settings)

        assert response.status_code == 429
        assert int(response["Retry-After"]) > 0

    def test_uses_the_problem_details_shape(self, client, settings) -> None:
        """One error shape everywhere (M1 T3) — including this one."""
        response = self._exhaust_resend(client, settings)

        assert response["Content-Type"] == "application/problem+json"
        assert response.json()["status"] == 429


class TestUploadUrlsAreRationed:
    """Each call to the upload endpoint signs a URL that can write to our
    bucket, so an unthrottled version is a way to mint write grants without
    ever uploading through us.

    This lives here rather than beside the upload tests for a concrete reason.
    DRF binds ``SimpleRateThrottle.THROTTLE_RATES`` as a *class attribute* when
    ``rest_framework.throttling`` is first imported, so whichever rates were
    active at that moment are frozen in. In a module whose fixtures raise every
    rate to 10000/hour, a per-test override never takes effect — the test
    reports success after the limit and reads exactly like an inert throttle.
    That is what this module's docstring means by using the real rates.
    """

    def _instructor_with_a_lesson(self):
        from apps.accounts.models import Role
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Language, Lesson, Section

        user = create_account(email="teacher@example.test", password=PASSWORD)
        user.role = Role.INSTRUCTOR
        user.save(update_fields=["role"])

        language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=user
        )
        section = Section.objects.create(course=course, title="Greetings", position=1)
        return Lesson.objects.create(
            course=course, section=section, slug="intro", title="Intro", position=1
        )

    @pytest.mark.django_db
    def test_upload_urls_stop_after_their_limit(self, client, settings) -> None:
        lesson = self._instructor_with_a_lesson()
        limit = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["media_upload"].split("/")[0])
        _post(client, LOGIN, {"email": "teacher@example.test", "password": PASSWORD})

        path = f"/api/v1/lessons/{lesson.id}/media/upload-url/"
        statuses = [
            _post(client, path, {"content_type": "video/mp4"}).status_code for _ in range(limit + 1)
        ]

        assert statuses[-1] == 429
        assert statuses[:limit] == [201] * limit


class TestProgressWritesAreRationed:
    """§10 M7 names "a progress write per second" as this milestone's mistake.

    Here rather than beside the progress tests for the reason this module's
    docstring gives, and which M5 learned the hard way: DRF binds
    `SimpleRateThrottle.THROTTLE_RATES` as a class attribute when
    `rest_framework.throttling` is first imported, so in a module whose
    fixtures raise every rate to 10000/hour a per-test override never takes
    effect and the test reads exactly like an inert throttle.
    """

    def _entitled_learner_with_a_lesson(self):
        from apps.accounts.models import Role
        from apps.accounts.services import create_account
        from apps.catalog.models import Course, Language, Lesson, Section
        from apps.catalog.services import approve, submit_for_review
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        instructor = create_account(email="teacher@example.test", password=PASSWORD)
        instructor.role = Role.INSTRUCTOR
        instructor.save(update_fields=["role"])
        admin = create_account(email="admin@example.test", password=PASSWORD)
        admin.role = Role.ADMIN
        admin.save(update_fields=["role"])

        language = Language.objects.create(code="es", name="Spanish", native_name="Espanol")
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
        )
        section = Section.objects.create(course=course, title="Greetings", position=1)
        lesson = Lesson.objects.create(
            course=course, section=section, slug="intro", title="Intro", position=1
        )
        submit_for_review(course=course, by=instructor)
        approve(course=course, by=admin)

        learner = create_account(email="learner@example.test", password=PASSWORD)
        start_subscription(user=learner, provider=FakeBillingProvider())
        return lesson

    @pytest.mark.django_db
    def test_heartbeats_stop_after_their_limit(self, client, settings) -> None:
        lesson = self._entitled_learner_with_a_lesson()
        limit = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["progress"].split("/")[0])
        _post(client, LOGIN, {"email": "learner@example.test", "password": PASSWORD})

        path = f"/api/v1/lessons/{lesson.id}/progress/"
        statuses = [
            client.put(
                path,
                {"position_seconds": beat * 15, "watched_delta_seconds": 15},
                content_type="application/json",
            ).status_code
            for beat in range(limit + 1)
        ]

        assert statuses[-1] == 429
        assert statuses[:limit] == [200] * limit
