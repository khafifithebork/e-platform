"""Email leaves the request path, behind an adapter.

Two things are being pinned, and the second is the one worth arguing about.

**The layering.** Nothing outside `notifications/providers/` sends mail. That
is a structural test, because a fifth call site reaching for `send_mail` would
be invisible to every behavioural test — the email still arrives.

**The honesty of the retry.** `test_a_redelivered_task_sends_again` asserts a
*duplicate*, which reads like a test of a bug. It is: delivery is at-least-once
and cannot be otherwise without state ADR-020 §8 declined to keep. Asserting
what actually happens is the alternative to a comment nobody reads, and it will
fail the day somebody adds idempotency — which is exactly when this file should
be revisited.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.core import mail

from apps.notifications.providers.base import EmailNotSent, OutboundEmail
from apps.notifications.providers.django_email import DjangoEmailProvider, email_provider
from apps.notifications.services import send_transactional_email

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class TestTheAdapter:
    def test_it_satisfies_the_interface(self) -> None:
        """`runtime_checkable`, so this is a real check rather than a comment
        that the classes look alike."""
        from apps.notifications.providers.base import EmailProvider

        assert isinstance(email_provider(), EmailProvider)

    def test_it_sends_through_django(self) -> None:
        DjangoEmailProvider().send(
            OutboundEmail(to="learner@example.test", subject="Hello", body="Body.")
        )

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["learner@example.test"]
        assert mail.outbox[0].subject == "Hello"

    def test_a_backend_that_accepts_nothing_is_a_failure(self, monkeypatch) -> None:
        """`send_mail` returns the number accepted. Zero without an exception
        is a backend declining quietly, and treating that as success is how a
        verification email is never sent and never reported."""
        monkeypatch.setattr(
            "apps.notifications.providers.django_email.send_mail", lambda **kwargs: 0
        )

        with pytest.raises(EmailNotSent):
            DjangoEmailProvider().send(
                OutboundEmail(to="learner@example.test", subject="Hello", body="Body.")
            )

    def test_a_backend_error_becomes_the_interface_error(self, monkeypatch) -> None:
        """So the task above can retry on one exception type rather than on
        whatever the current backend happens to raise."""

        def explode(**kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr("apps.notifications.providers.django_email.send_mail", explode)

        with pytest.raises(EmailNotSent):
            DjangoEmailProvider().send(
                OutboundEmail(to="learner@example.test", subject="Hello", body="Body.")
            )


class TestTheService:
    def test_it_queues_rather_than_sends(self, monkeypatch) -> None:
        """The point of T6: the service hands the message to Celery and does
        not send it. The empty outbox is half the assertion — the other half is
        that `deliver_email.delay` was the thing called."""
        called = {}

        def fake_delay(**kwargs):
            called.update(kwargs)

        monkeypatch.setattr("apps.notifications.services.deliver_email.delay", fake_delay)

        send_transactional_email(to="learner@example.test", subject="Hi", body="Body.")

        assert called == {"to": "learner@example.test", "subject": "Hi", "body": "Body."}
        assert mail.outbox == []

    def test_and_the_task_really_delivers(self) -> None:
        """The twin. A service that queued into a void would satisfy the test
        above perfectly.

        Applied synchronously rather than through `.delay()`, which is this
        suite's convention for every task (see `test_media_processing.py`) and
        is not optional: Celery is **not** configured eager here, so `.delay()`
        opens a broker connection and a unit test starts depending on Redis
        being up.
        """
        from apps.notifications import tasks

        tasks.deliver_email.apply(
            kwargs={"to": "learner@example.test", "subject": "Hi", "body": "Body."}
        ).get()

        assert [message.to for message in mail.outbox] == [["learner@example.test"]]


class TestTheTask:
    def test_it_retries_when_the_provider_refuses(self, monkeypatch) -> None:
        """Bounded and only on refusal: `EmailNotSent` means the provider did
        not take it. Any other exception is our bug, and retrying a bug three
        times produces three tracebacks."""
        from apps.notifications import tasks

        attempts = {"count": 0}

        class Refusing:
            name = "refusing"

            def send(self, message):
                attempts["count"] += 1
                raise EmailNotSent("nope")

        monkeypatch.setattr(tasks, "email_provider", lambda: Refusing())

        with pytest.raises(EmailNotSent):
            tasks.deliver_email.apply(
                kwargs={"to": "a@example.test", "subject": "s", "body": "b"}
            ).get()

        # `.apply()` runs the task inline, retries included — the M5 finding
        # that a test watching for a `Retry` exception reports "did not raise".
        # So the observable evidence that retry is configured is the attempt
        # count, not an exception type.
        assert attempts["count"] > 1

    def test_it_does_not_retry_our_own_bugs(self, monkeypatch) -> None:
        """The twin for the line above. `autoretry_for` naming a broad
        exception would make every programming error a four-times-repeated
        one."""
        from apps.notifications import tasks

        attempts = {"count": 0}

        class Broken:
            name = "broken"

            def send(self, message):
                attempts["count"] += 1
                raise TypeError("a bug, not a refusal")

        monkeypatch.setattr(tasks, "email_provider", lambda: Broken())

        with pytest.raises(TypeError):
            tasks.deliver_email.apply(
                kwargs={"to": "a@example.test", "subject": "s", "body": "b"}
            ).get()

        assert attempts["count"] == 1

    def test_a_redelivered_task_sends_again(self) -> None:
        """Delivery is **at-least-once**, and this asserts the duplicate rather
        than implying otherwise.

        Celery with `acks_late` redelivers a task whose worker died after the
        provider accepted the message, and nothing here can tell that apart
        from a task that never ran. Preventing it needs state ADR-020 §8
        declined to keep, or a provider idempotency key that does not exist
        yet. A duplicate verification email is a nuisance, not a hazard.

        **This test failing is good news**: it means somebody added
        idempotency, and this file is where the claim needs updating.
        """
        from apps.notifications import tasks

        payload = {"to": "a@example.test", "subject": "s", "body": "b"}
        tasks.deliver_email.apply(kwargs=payload).get()
        tasks.deliver_email.apply(kwargs=payload).get()

        assert len(mail.outbox) == 2

    def test_the_address_is_not_logged(self, caplog) -> None:
        """It is personal data and this log is shipped somewhere. "An email was
        sent" is the operationally useful half."""
        from apps.notifications import tasks

        with caplog.at_level("INFO"):
            tasks.deliver_email.apply(
                kwargs={"to": "learner@example.test", "subject": "s", "body": "b"}
            ).get()

        assert "learner@example.test" not in caplog.text


class TestNothingElseSendsMail:
    """The structural guard. A fifth call site reaching for `send_mail`
    directly is invisible to every behavioural test, because the email still
    arrives — it just arrives from inside a request, unretried, from a layer
    that should not know how."""

    PERMITTED = "apps/notifications/providers/django_email.py"

    @staticmethod
    def _senders() -> set[str]:
        found: set[str] = set()
        for path in (BACKEND_ROOT / "apps").rglob("*.py"):
            relative = path.relative_to(BACKEND_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "django.core.mail":
                    found.add(relative)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"send_mail", "send_mass_mail"}
                ):
                    found.add(relative)
        return found

    def test_only_the_adapter_touches_djangos_mail_api(self) -> None:
        assert self._senders() == {self.PERMITTED}

    def test_the_guard_recognises_what_it_looks_for(self) -> None:
        """The twin. A guard that found nothing would equal an empty set and
        pass forever — which is the failure this codebase keeps finding in its
        own guards."""
        assert self.PERMITTED in self._senders()
