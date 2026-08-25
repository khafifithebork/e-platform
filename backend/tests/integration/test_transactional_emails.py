"""The transactional set. Abuse cases 7 and 9.

Two things here are easy to get wrong and are pinned deliberately.

**`transaction.on_commit` never fires under pytest-django** unless the test
captures it — an M5 finding, recorded in ADR-013 §5, and it makes a
notification look absent when the code is correct. Every review test here uses
`django_capture_on_commit_callbacks(execute=True)`, and
`test_it_does_not_send_before_the_transaction_commits` is the twin proving the
deferral is real rather than incidental.

**Abuse case 9 reads differently for plain text.** There is no HTML email, so
there is nothing to escape; autoescaping is off precisely so `O'Brien` is not
greeted as `O&#x27;Brien`. The control that matters for a text mailer is header
injection — a newline in a subject — and `BadHeaderError` is what stands
between a course title and a forged `Bcc:`.
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
    """`User` carries no name field — `display_name` lives on
    `StudentProfile`, which an instructor need not have.

    Verified by default. `create_account` leaves an address unconfirmed, and
    abuse case 7 refuses every message outside verification and password reset
    to an unconfirmed one — so an unverified fixture would make these tests
    about that rule rather than about the message under test. The rule itself
    is tested in `test_email_abuse_cases.py`.
    """
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


def _submitted_course(*, title="Spanish Basics", instructor=None):
    from apps.accounts.models import Role
    from apps.catalog.models import Course, Language

    instructor = instructor or _user("teacher@example.test", role=Role.INSTRUCTOR)
    language, _ = Language.objects.get_or_create(
        code="es", defaults={"name": "Spanish", "native_name": "Espanol"}
    )
    return Course.objects.create(
        slug="spanish-basics",
        title=title,
        language=language,
        level="A1",
        instructor=instructor,
    )


class TestTheAccountMessages:
    def test_registration_sends_a_verification_email(self, client) -> None:
        client.post(
            "/api/v1/auth/register/",
            {"email": "learner@example.test", "password": PASSWORD},
            content_type="application/json",
        )

        assert [message.subject for message in mail.outbox] == ["Verify your email address"]

    def test_a_password_change_sends_a_notice(self, client) -> None:
        """The person who most needs to know is the one who did not do it."""
        _user("learner@example.test")
        client.post(
            "/api/v1/auth/login/",
            {"email": "learner@example.test", "password": PASSWORD},
            content_type="application/json",
        )
        mail.outbox.clear()

        response = client.post(
            "/api/v1/auth/password/change/",
            {"current_password": PASSWORD, "new_password": "another-long-passphrase"},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert [message.subject for message in mail.outbox] == ["Your password was changed"]

    def test_the_notice_carries_no_link(self) -> None:
        """A security notice that asks you to click something is a template
        anyone can copy."""
        from apps.notifications.emails import send_password_changed_email

        _user("learner@example.test")

        send_password_changed_email(to="learner@example.test")

        assert "http" not in mail.outbox[0].body.lower()


class TestTheReviewMessages:
    def test_submitting_tells_every_administrator(
        self, client, django_capture_on_commit_callbacks
    ) -> None:
        from apps.accounts.models import Role
        from apps.catalog.services import submit_for_review

        _user("admin-a@example.test", role=Role.ADMIN)
        _user("admin-b@example.test", role=Role.ADMIN)
        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        course = _submitted_course(instructor=instructor)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            submit_for_review(course=course, by=instructor)

        assert sorted(message.to[0] for message in mail.outbox) == [
            "admin-a@example.test",
            "admin-b@example.test",
        ]

    def test_one_message_each_rather_than_one_with_everybody_on_it(
        self, django_capture_on_commit_callbacks
    ) -> None:
        """A bcc list is how a transactional message reaches somebody it was
        not about."""
        from apps.accounts.models import Role
        from apps.catalog.services import submit_for_review

        _user("admin-a@example.test", role=Role.ADMIN)
        _user("admin-b@example.test", role=Role.ADMIN)
        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        course = _submitted_course(instructor=instructor)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            submit_for_review(course=course, by=instructor)

        assert all(len(message.to) == 1 for message in mail.outbox)

    def test_approving_tells_the_instructor(self, django_capture_on_commit_callbacks) -> None:
        from apps.accounts.models import Role
        from apps.catalog.services import approve, submit_for_review

        admin = _user("admin@example.test", role=Role.ADMIN)
        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        course = _submitted_course(instructor=instructor)
        with django_capture_on_commit_callbacks(execute=True):
            submit_for_review(course=course, by=instructor)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            approve(course=course, by=admin)

        assert [message.to for message in mail.outbox] == [["teacher@example.test"]]
        assert "Approved" in mail.outbox[0].body

    def test_rejecting_carries_the_reviewers_words(
        self, django_capture_on_commit_callbacks
    ) -> None:
        from apps.accounts.models import Role
        from apps.catalog.services import reject, submit_for_review

        admin = _user("admin@example.test", role=Role.ADMIN)
        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        course = _submitted_course(instructor=instructor)
        with django_capture_on_commit_callbacks(execute=True):
            submit_for_review(course=course, by=instructor)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            reject(course=course, by=admin, notes="The audio is inaudible in lesson 2.")

        assert "inaudible in lesson 2" in mail.outbox[0].body

    def test_an_approval_with_no_notes_says_so(self, django_capture_on_commit_callbacks) -> None:
        """Rather than an empty section that reads like a rendering bug."""
        from apps.accounts.models import Role
        from apps.catalog.services import approve, submit_for_review

        admin = _user("admin@example.test", role=Role.ADMIN)
        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        course = _submitted_course(instructor=instructor)
        with django_capture_on_commit_callbacks(execute=True):
            submit_for_review(course=course, by=instructor)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            approve(course=course, by=admin)

        assert "no notes" in mail.outbox[0].body.lower()

    def test_it_does_not_send_before_the_transaction_commits(self) -> None:
        """The twin for every `capture_on_commit` above. Without the deferral
        an approval that rolled back would still have told the instructor their
        course was live.

        No capture fixture here, deliberately: under pytest-django the outer
        test transaction never commits, so an `on_commit` callback that is
        genuinely deferred never runs — and an empty outbox is the evidence.
        """
        from apps.accounts.models import Role
        from apps.catalog.services import approve, submit_for_review

        admin = _user("admin@example.test", role=Role.ADMIN)
        instructor = _user("teacher@example.test", role=Role.INSTRUCTOR)
        course = _submitted_course(instructor=instructor)
        submit_for_review(course=course, by=instructor)
        mail.outbox.clear()

        approve(course=course, by=admin)

        assert mail.outbox == []


class TestRenderingCannotBeUsedAgainstUs:
    """Abuse case 9, read for a text-only mailer."""

    def test_a_newline_in_a_title_cannot_forge_a_header(
        self, django_capture_on_commit_callbacks
    ) -> None:
        """The real injection vector when there is no HTML.

        Refused when the message is built, not when it is sent. Django's own
        `BadHeaderError` arrives at send time — inside a retrying task — so an
        injected newline would become four SMTP attempts for something that
        can never succeed.
        """
        from apps.notifications.emails import send_course_submitted_email

        _user("admin@example.test")

        with pytest.raises(ValueError):
            send_course_submitted_email(
                to="admin@example.test",
                course_title="Spanish\nBcc: attacker@example.test",
                instructor_name="Ada",
            )

    def test_an_apostrophe_survives_intact(self) -> None:
        """Autoescaping is off because this is plain text. With it on, an
        instructor called O'Brien is greeted as O&#x27;Brien — a bug nobody
        reports because it looks like a mail client problem."""
        from apps.notifications.emails import send_course_submitted_email

        _user("admin@example.test")

        send_course_submitted_email(
            to="admin@example.test",
            course_title="Reading & Writing",
            instructor_name="Aoife O'Brien",
        )

        assert "O'Brien" in mail.outbox[0].body
        assert "Reading & Writing" in mail.outbox[0].subject
        assert "&amp;" not in mail.outbox[0].subject

    def test_no_html_template_has_appeared(self) -> None:
        """The moment one does, autoescaping stops being a formatting choice
        and becomes a real control — and the docstrings in `emails.py` become
        wrong. This is what makes that arrival loud."""
        from pathlib import Path

        templates = Path(__file__).resolve().parents[2] / "apps" / "notifications" / "templates"

        assert list(templates.rglob("*.html")) == []

    def test_every_template_pair_exists(self) -> None:
        """A missing template is a `TemplateDoesNotExist` at send time, which
        in production is a task that retries three times and gives up."""
        from apps.notifications import emails

        for name in (
            "verification",
            "password_reset",
            "password_changed",
            "course_submitted",
            "course_reviewed",
        ):
            subject, body = emails._render(name, {"token": "t", "course_title": "c", "notes": ""})
            assert subject.strip(), name
            assert body.strip(), name

    def test_a_subject_never_ends_up_multiline(self) -> None:
        """Both templates are stripped, and a trailing newline in a file is the
        ordinary way a subject becomes a malformed header."""
        from apps.notifications import emails

        subject, _ = emails._render("verification", {"token": "t"})

        assert "\n" not in subject
