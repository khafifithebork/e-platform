"""Exporting your own data — GDPR Article 15 and 20.

`docs/specs/m10-admin.md` §6 deferred this deliberately: "Erasure obligations are
real and are their own piece of work; `actor_label` is here so the audit trail is
ready for it, not because M10 implements it." The export half is the tractable half —
it destroys nothing and conflicts with no retention obligation — and this is it.
ADR-036 records the decisions.

The tests that carry weight are the exclusions. Anyone can see that a field is
present; the interesting properties are the four things that must **not** be in the
file, and one of them is another person's name.
"""

from __future__ import annotations

import json

import pytest

EXPORT = "/api/v1/auth/me/export/"
LOGIN = "/api/v1/auth/login/"
PASSWORD = "a-sufficiently-long-passphrase"


@pytest.fixture(autouse=True)
def _generous_throttles(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": dict.fromkeys(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "10000/hour"
        ),
    }


@pytest.fixture
def account(db):
    from apps.accounts.services import create_account

    return create_account(email="learner@example.test", password=PASSWORD)


def _sign_in(client, account):
    client.post(
        LOGIN, {"email": account.email, "password": PASSWORD}, content_type="application/json"
    )


@pytest.mark.django_db
class TestRequiresAuthentication:
    def test_anonymous_is_refused(self, client) -> None:
        """The endpoint that returns everything about one person is the one where
        this matters most."""
        assert client.get(EXPORT).status_code in (401, 403)

    def test_the_refusal_is_a_problem_document(self, client) -> None:
        assert client.get(EXPORT)["Content-Type"] == "application/problem+json"

    def test_after_logout_it_is_refused_again(self, client, account) -> None:
        _sign_in(client, account)
        client.post("/api/v1/auth/logout/", content_type="application/json")

        assert client.get(EXPORT).status_code in (401, 403)


@pytest.mark.django_db
class TestIdentityComesOnlyFromTheSession:
    """The same property `/auth/me/` has, and for a much higher stake.

    There is no path, query or header parameter that selects a user, so there is
    nothing to manipulate — architecture.md §4.4 calls fetching by a
    client-supplied identifier the most common IDOR in DRF codebases.
    """

    def test_a_query_parameter_cannot_export_another_user(self, client, account) -> None:
        from apps.accounts.services import create_account

        other = create_account(email="someone.else@example.test", password=PASSWORD)
        _sign_in(client, account)

        for attempt in (f"?id={other.id}", f"?user={other.id}", f"?email={other.email}"):
            body = client.get(f"{EXPORT}{attempt}").json()

            assert body["account"]["email"] == account.email
            assert other.email not in json.dumps(body)

    def test_a_header_cannot_export_another_user(self, client, account) -> None:
        from apps.accounts.services import create_account

        other = create_account(email="someone.else@example.test", password=PASSWORD)
        _sign_in(client, account)

        body = client.get(EXPORT, headers={"x-user-id": str(other.id)}).json()

        assert body["account"]["email"] == account.email


@pytest.mark.django_db
class TestWhatItContains:
    def test_the_account_itself(self, client, account) -> None:
        _sign_in(client, account)

        body = client.get(EXPORT).json()

        assert body["account"]["email"] == account.email
        assert body["account"]["id"] == str(account.id)
        assert body["account"]["email_confirmed"] is False
        assert body["account"]["registered_at"]

    def test_says_what_it_is_and_when_it_was_made(self, client, account) -> None:
        """An export is saved and opened much later. A file that does not say what
        it is or when it was taken is a puzzle rather than a record."""
        _sign_in(client, account)

        export = client.get(EXPORT).json()["export"]

        assert export["generated_at"]
        assert "course content is not included" in export["about"].lower()

    def test_points_at_no_documentation_that_does_not_exist(self, client, account) -> None:
        """The first draft of `about` ended "See the privacy documentation for what
        that covers", and there is no privacy documentation — that page is blocked on
        owner-supplied content.

        Referring somebody exercising a data-access right to a page that does not
        exist is worse than saying nothing, so this pins the absence of any pointer.
        The same fault, caught in the same session, nearly put an invented support
        address on the account page.
        """
        _sign_in(client, account)

        about = client.get(EXPORT).json()["export"]["about"].lower()

        for pointer in ("see the", "privacy policy", "privacy documentation", "http", "@"):
            assert pointer not in about, pointer

    def test_every_section_is_present_even_when_empty(self, client, account) -> None:
        """A fresh account exports empty lists, not missing keys.

        An absent key reads as "we hold nothing of this kind about you"; an empty
        list says "we hold none *yet*". Only one of those is true, and a consumer
        writing `body["subscriptions"]` should not have to guess.
        """
        _sign_in(client, account)

        body = client.get(EXPORT).json()

        for section in (
            "courses_started",
            "lesson_progress",
            "subscriptions",
            "manual_access_grants",
        ):
            assert body[section] == [], section

    def test_courses_and_progress_in_readable_terms(self, client, account) -> None:
        """Slugs and titles, not only UUIDs.

        A progress row saying `lesson: 9f3c…` is technically complete and useless to
        the person who asked for it. Article 20 is about portability, and data
        nobody can read is not portable.
        """
        from django.utils import timezone

        from apps.accounts.services import create_account
        from apps.catalog.models import Course, CourseStatus, Language, Lesson, LessonType, Section
        from apps.learning.models import Enrollment, LessonProgress

        language = Language.objects.create(code="es", name="Spanish")
        instructor = create_account(email="teacher@example.test", password=PASSWORD)
        course = Course.objects.create(
            title="Spanish for beginners",
            slug="spanish",
            language=language,
            level="A1",
            instructor=instructor,
            status=CourseStatus.PUBLISHED,
            # Required by `course_published_has_published_at`, a database check
            # constraint (invariant 11). The first version of this fixture omitted
            # it and the constraint refused the row — which is the constraint
            # working, in a test that was not about it.
            published_at=timezone.now(),
        )
        section = Section.objects.create(course=course, title="Getting started", position=1)
        lesson = Lesson.objects.create(
            course=course,
            section=section,
            title="The alphabet",
            slug="alphabet",
            position=1,
            lesson_type=LessonType.VIDEO,
        )
        Enrollment.objects.create(user=account, course=course, last_lesson=lesson)
        LessonProgress.objects.create(
            user=account,
            lesson=lesson,
            last_position_seconds=42,
            # `max_position_is_at_least_last` is a database check constraint
            # (invariant 11) and it refused the row when this was left at its
            # default of 0. Another constraint catching a fixture rather than a bug.
            max_position_seconds=42,
            watched_seconds=40,
        )

        _sign_in(client, account)
        body = client.get(EXPORT).json()

        assert body["courses_started"] == [
            {
                "course": "spanish",
                "course_title": "Spanish for beginners",
                "started_at": body["courses_started"][0]["started_at"],
                "completed_at": None,
                "resume_at_lesson": "alphabet",
            }
        ]
        assert body["lesson_progress"][0]["lesson"] == "alphabet"
        assert body["lesson_progress"][0]["lesson_title"] == "The alphabet"
        assert body["lesson_progress"][0]["course"] == "spanish"
        assert body["lesson_progress"][0]["last_position_seconds"] == 42
        assert body["lesson_progress"][0]["watched_seconds"] == 40

    def test_the_subscription_and_its_history(self, client, account) -> None:
        """The history matters more than the status.

        `SubscriptionEvent` exists because "a mutable status answers *what is true
        now*; it cannot answer *why is this person's access wrong*". That is the
        question somebody exports their data to answer.
        """
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        start_subscription(user=account, provider=FakeBillingProvider())
        _sign_in(client, account)

        [subscription] = client.get(EXPORT).json()["subscriptions"]

        assert subscription["status"]
        assert subscription["provider"] == "fake"
        assert len(subscription["history"]) >= 1
        assert subscription["history"][0]["at"]

    def test_a_manual_grant_without_the_administrator_who_made_it(self, client, account) -> None:
        """**The exclusion that is easiest to get wrong.**

        An override is the person's own data — they are entitled to know a grant
        exists, when it runs and why. `granted_by` names *another person*, and
        Article 15 does not extend to other people's data. Including the row while
        excluding that one field is the whole point.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.services import create_account
        from apps.entitlements.models import AccessOverride

        admin = create_account(email="staff.member@example.test", password=PASSWORD)
        AccessOverride.objects.create(
            user=account,
            granted_by=admin,
            reason="Compensation for the outage in March",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=30),
        )

        _sign_in(client, account)
        raw = client.get(EXPORT).content.decode()
        [grant] = client.get(EXPORT).json()["manual_access_grants"]

        assert grant["reason"] == "Compensation for the outage in March"
        assert grant["starts_at"] and grant["ends_at"]
        # The administrator's identity, in every form it could leak.
        assert "staff.member@example.test" not in raw
        assert str(admin.id) not in raw
        assert "granted_by" not in raw


@pytest.mark.django_db
class TestWhatItMustNotContain:
    def test_no_password_material(self, client, account) -> None:
        _sign_in(client, account)
        raw = client.get(EXPORT).content.decode().lower()

        assert "password" not in raw
        assert "argon2" not in raw

    def test_no_token_hashes(self, client, account) -> None:
        """Registration issues a verification token, so a hash exists by now. A
        hash discloses nothing and is the one thing here that must never leave the
        database — exporting it would be a credential in a file people email."""
        from apps.accounts.models import EmailVerificationToken
        from apps.accounts.services import issue_email_verification

        # Issued explicitly. `create_account` does not do this — `RegisterView`
        # does, after calling it — and the first version of this test assumed
        # otherwise and asserted against an empty table, which would have passed
        # its real assertions for the wrong reason.
        issue_email_verification(user=account)
        assert EmailVerificationToken.objects.filter(user=account).exists()

        _sign_in(client, account)
        raw = client.get(EXPORT).content.decode()

        stored = EmailVerificationToken.objects.filter(user=account).first()
        assert stored is not None
        assert stored.token_hash not in raw
        assert "token_hash" not in raw

    def test_no_audit_log(self, client, account) -> None:
        """Each row carries an `actor_label` naming the administrator who acted.
        Handing over a log of who touched an account discloses staff identities to
        anyone who asks; if a regulator ever requires it, the answer is a redacted
        projection rather than this."""
        from apps.core.models import AuditLog

        AuditLog.objects.create(
            action="user.role_changed",
            actor_label="admin@example.test",
            target_type="accounts.User",
            target_id=str(account.id),
            metadata={"from": "STUDENT", "to": "INSTRUCTOR"},
        )

        _sign_in(client, account)
        raw = client.get(EXPORT).content.decode()

        assert "admin@example.test" not in raw
        assert "user.role_changed" not in raw

    def test_no_internal_permission_flags(self, client, account) -> None:
        _sign_in(client, account)
        body = client.get(EXPORT).json()

        for field in ("is_staff", "is_superuser", "user_permissions", "groups"):
            assert field not in body["account"]


@pytest.mark.django_db
class TestTheResponseItself:
    def test_is_sent_as_a_download(self, client, account) -> None:
        _sign_in(client, account)
        response = client.get(EXPORT)

        assert "attachment" in response["Content-Disposition"]
        assert str(account.id) in response["Content-Disposition"]

    def test_the_filename_does_not_carry_the_address(self, client, account) -> None:
        """An export gets saved and forwarded. An email address in the filename is
        an email address in every directory listing and mail client that touches
        it afterwards."""
        _sign_in(client, account)

        assert account.email not in client.get(EXPORT)["Content-Disposition"]

    def test_is_not_cachable(self, client, account) -> None:
        """A GET, so caches will try. An export left in a shared proxy or a disk
        cache is somebody's whole profile on a machine they borrowed."""
        _sign_in(client, account)

        assert "no-store" in client.get(EXPORT)["Cache-Control"]


@pytest.mark.django_db
class TestQueryCount:
    def test_does_not_fan_out_per_row(self, client, account, django_assert_num_queries) -> None:
        """Fixed regardless of how much the learner has done.

        Two courses, four lessons, progress on all of them and a subscription with
        its history — written the obvious way, each progress row costs a query for
        its course and each subscription one for its events, which is the N+1 that
        turns a committed learner's export into a timeout.

        **Eight queries, counted rather than estimated.** In order: the session; the
        user, from the authentication middleware; the student profile, read lazily
        for `display_name`; enrolments; progress; subscriptions; the subscription
        events prefetch; overrides.

        The first version of this docstring said eight and the test measured seven —
        because the fixture had no subscription, so `prefetch_related` skipped its
        second query entirely. That is worth recording: a prefetch on an empty outer
        queryset costs nothing, so a fixture with no rows cannot prove the prefetch
        works. **The subscription is here to make the eighth query happen.**

        Pinned so a ninth has to be argued for.
        """
        from django.utils import timezone

        from apps.accounts.services import create_account
        from apps.catalog.models import Course, CourseStatus, Language, Lesson, LessonType, Section
        from apps.learning.models import Enrollment, LessonProgress

        language = Language.objects.create(code="es", name="Spanish")
        instructor = create_account(email="teacher@example.test", password=PASSWORD)

        for course_index in range(2):
            course = Course.objects.create(
                title=f"Course {course_index}",
                slug=f"course-{course_index}",
                language=language,
                level="A1",
                instructor=instructor,
                status=CourseStatus.PUBLISHED,
                published_at=timezone.now(),
            )
            section = Section.objects.create(course=course, title="One", position=1)
            Enrollment.objects.create(user=account, course=course)

            for lesson_index in range(2):
                lesson = Lesson.objects.create(
                    course=course,
                    section=section,
                    title=f"Lesson {lesson_index}",
                    slug=f"lesson-{course_index}-{lesson_index}",
                    position=lesson_index + 1,
                    lesson_type=LessonType.VIDEO,
                )
                LessonProgress.objects.create(user=account, lesson=lesson, watched_seconds=10)

        # A subscription with history, so the events prefetch is exercised rather
        # than skipped. See the docstring.
        from apps.entitlements.providers.fake import FakeBillingProvider
        from apps.entitlements.services import start_subscription

        start_subscription(user=account, provider=FakeBillingProvider())

        _sign_in(client, account)

        with django_assert_num_queries(8):
            client.get(EXPORT)
