"""The M11 abuse cases nothing else covers: 3, 7, 8 and 10.

Cases 1, 2, 4, 5, 6 and 9 are covered where the feature lives —
`test_course_search.py`, `test_related_courses.py`, `test_catalogue_filters.py`
and `test_transactional_emails.py`. They are not repeated here.

**Case 8 is asserted as unmet.** "A retried email task does not send twice" is
not true and cannot be made true without state ADR-020 §8 declined to keep.
The test says so out loud rather than being quietly omitted, because a missing
test and a satisfied one look identical in a summary.
"""

from __future__ import annotations

import pytest
from django.core import mail

PASSWORD = "a-long-enough-passphrase"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


def _user(email: str, *, role=None, verified: bool = True):
    from apps.accounts.services import create_account

    user = create_account(email=email, password=PASSWORD)
    fields = []
    if role:
        user.role = role
        fields.append("role")
    if verified:
        user.is_email_verified = True
        fields.append("is_email_verified")
    if fields:
        user.save(update_fields=fields)
    return user


def _published_course(slug="spanish", title="Spanish Basics"):
    from django.utils import timezone

    from apps.accounts.models import Role
    from apps.catalog.models import Course, CourseStatus, Language
    from apps.catalog.services import refresh_search_vector

    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Espanol"}
    )
    course = Course.objects.create(
        slug=slug,
        title=title,
        language=language,
        level="A1",
        instructor=_user(f"{slug}-teacher@example.test", role=Role.INSTRUCTOR),
    )
    Course.objects.filter(pk=course.pk).update(
        status=CourseStatus.PUBLISHED, published_at=timezone.now()
    )
    course.refresh_from_db()
    refresh_search_vector(course=course)
    return course


class TestCaseThreeSearchLeaksNothingPrivate:
    """Swept over the whole response rather than checked field by field: the
    risk is a field nobody thought to exclude, and a named-field assertion only
    covers the ones somebody remembered."""

    FORBIDDEN = ("search_vector", "body", "provider", "instructor_id", "status", "@example.test")

    def test_a_search_result_carries_none_of_them(self, client) -> None:
        _published_course()

        raw = client.get("/api/v1/catalogue/search/", {"q": "spanish"}).content.decode()

        for needle in self.FORBIDDEN:
            assert needle not in raw, needle

    def test_nor_does_a_course_detail(self, client) -> None:
        """The related strip renders through the same serializer, so the same
        sweep has to hold where it is embedded."""
        course = _published_course()
        _published_course(slug="neighbour", title="Spanish More")

        raw = client.get(f"/api/v1/catalogue/courses/{course.slug}/").content.decode()

        for needle in self.FORBIDDEN:
            assert needle not in raw, needle

    def test_the_sweep_would_notice(self, client) -> None:
        """The twin. Every assertion above is a negative, and a sweep looking
        for strings that never appear anywhere would pass over an empty
        response."""
        _published_course()

        raw = client.get("/api/v1/catalogue/search/", {"q": "spanish"}).content.decode()

        assert "spanish" in raw.lower()


class TestCaseSevenUnverifiedAddresses:
    def test_a_password_change_notice_is_withheld_from_an_unverified_address(self) -> None:
        from apps.notifications.emails import send_password_changed_email

        _user("unconfirmed@example.test", verified=False)

        send_password_changed_email(to="unconfirmed@example.test")

        assert mail.outbox == []

    def test_and_withholding_it_does_not_break_the_password_change(self, client) -> None:
        """The reason this withholds rather than raises. A notification is
        secondary to the thing it reports: it may decline to go out, it may not
        take the action down with it. The first version raised, and an
        unverified learner changing their password got a 500."""
        _user("unconfirmed@example.test", verified=False)
        client.post(
            "/api/v1/auth/login/",
            {"email": "unconfirmed@example.test", "password": PASSWORD},
            content_type="application/json",
        )

        response = client.post(
            "/api/v1/auth/password/change/",
            {"current_password": PASSWORD, "new_password": "another-long-passphrase"},
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_a_review_notice_is_withheld_too(self) -> None:
        from apps.notifications.emails import send_course_reviewed_email

        _user("unconfirmed@example.test", verified=False)

        sent = send_course_reviewed_email(
            to="unconfirmed@example.test",
            course_title="Spanish",
            decision="Approved",
            notes="",
        )

        assert sent is False
        assert mail.outbox == []

    def test_an_address_with_no_account_is_withheld(self) -> None:
        """Not merely "unverified" — unknown. An address nobody has an account
        for cannot have confirmed anything."""
        from apps.notifications.emails import send_password_changed_email

        send_password_changed_email(to="stranger@example.test")

        assert mail.outbox == []

    def test_but_verification_itself_still_reaches_an_unverified_address(self) -> None:
        """The exemption, and the reason it is not a loophole: this message
        exists to reach an address nobody has confirmed."""
        from apps.notifications.emails import send_verification_email

        send_verification_email(to="unconfirmed@example.test", token="tok")

        assert [message.to for message in mail.outbox] == [["unconfirmed@example.test"]]

    def test_and_so_does_a_password_reset(self) -> None:
        """Otherwise an unverified account is unrecoverable rather than merely
        unverified."""
        from apps.notifications.emails import send_password_reset_email

        send_password_reset_email(to="unconfirmed@example.test", token="tok")

        assert len(mail.outbox) == 1

    def test_the_exemptions_are_a_closed_list(self) -> None:
        """Two names, written down. A third exemption should be a visible edit
        rather than a check somebody forgot to add."""
        from apps.notifications.emails import REACHES_UNVERIFIED

        assert {"verification", "password_reset"} == REACHES_UNVERIFIED


class TestCaseEightIsNotMet:
    """**Asserted, not skipped.** Delivery is at-least-once.

    Celery with `acks_late` redelivers a task whose worker died after the
    provider accepted the message, and nothing can distinguish that from a task
    that never ran. Preventing it needs either an idempotency table — which
    ADR-020 §8 declined, because the question it answers belongs to a provider
    that does not exist yet — or a provider-side idempotency key, which arrives
    with Resend.

    A duplicate verification email is a nuisance rather than a hazard, which is
    why this is recorded rather than fixed. The spec sentence is reworded in
    T8 so the document stops claiming a guarantee the code does not make.
    """

    def test_a_redelivered_task_sends_a_second_copy(self) -> None:
        from apps.notifications import tasks

        payload = {"to": "learner@example.test", "subject": "s", "body": "b"}
        tasks.deliver_email.apply(kwargs=payload).get()
        tasks.deliver_email.apply(kwargs=payload).get()

        assert len(mail.outbox) == 2

    def test_nothing_records_that_a_message_was_sent(self) -> None:
        """The structural half. If a table appears, at-most-once becomes
        reachable and this whole class needs revisiting — so the absence is
        pinned rather than assumed."""
        from django.apps import apps as django_apps

        models = {
            model.__name__ for model in django_apps.get_app_config("notifications").get_models()
        }

        assert models == set()


class TestCaseTenTheVectorIsNotWritable:
    def test_it_is_absent_from_the_instructor_serializer(self) -> None:
        from apps.catalog.serializers import CourseSerializer

        assert "search_vector" not in CourseSerializer().fields

    def test_the_api_ignores_it_in_a_request_body(self, client) -> None:
        """Sent anyway, because "absent from the serializer" and "cannot be
        written" are different claims and only the second one matters."""
        from apps.accounts.models import Role
        from apps.catalog.models import Course, Language

        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        language, _ = Language.objects.get_or_create(
            code="es", defaults={"name": "Spanish", "native_name": "Espanol"}
        )
        course = Course.objects.create(
            slug="spanish", title="Spanish", language=language, level="A1", instructor=instructor
        )
        client.post(
            "/api/v1/auth/login/",
            {"email": "teacher@example.test", "password": PASSWORD},
            content_type="application/json",
        )

        response = client.patch(
            f"/api/v1/instructor/courses/{course.id}/",
            {"title": "Spanish", "search_vector": "'attacker':1A"},
            content_type="application/json",
        )

        assert response.status_code == 200
        course.refresh_from_db()
        assert "attacker" not in str(course.search_vector)

    def test_the_field_is_not_editable_at_the_model(self) -> None:
        """`editable=False` is what keeps it out of every ModelForm and every
        ModelSerializer at once, including ones nobody has written yet."""
        from apps.catalog.models import Course

        assert Course._meta.get_field("search_vector").editable is False
