"""The `request_id` chain, all three hops. M14 T2, abuse cases 1 and 2.

architecture.md §3.7 asks for the id to be propagated *"from Next.js → Django →
Celery"*, and says of it: **"Without this, debugging is archaeology."** Only the
middle hop existed. These tests cover the ends.

The case the whole thing exists for is concrete: an upload returns 202, the
lesson later has no subtitles, and somebody has to join the failing task back
to the request that queued it. `test_the_two_handlers_round_trip_an_id` is that
case, at the boundary this project actually owns.

**The two abuse cases are both about not trusting the value.** It arrives from
a browser over HTTP and from a broker over the network, and it ends up written
into a log line — so a crafted one is log injection into whatever aggregates
those lines. Django already sanitises the HTTP hop; the queue hop is new and is
sanitised for the same reason.
"""

from __future__ import annotations

import logging

import pytest

from apps.core.logging import MAX_REQUEST_ID_LENGTH, NO_REQUEST, request_id_var
from apps.core.middleware import REQUEST_ID_HEADER

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_context():
    """Each test starts with nothing in flight.

    The `ContextVar` is process-global, and a test that inherited the previous
    test's id would pass for the wrong reason — which is the same failure the
    `task_postrun` handler exists to prevent in a worker.
    """
    token = request_id_var.set("")
    yield
    request_id_var.reset(token)


class TestTheHttpHop:
    def test_a_supplied_id_is_echoed_back(self, client) -> None:
        """The property the browser hop depends on: send an id, get the same
        one back, and one query returns both sides."""
        response = client.get("/healthz", headers={REQUEST_ID_HEADER: "web-abc123"})

        assert response.headers[REQUEST_ID_HEADER] == "web-abc123"

    def test_an_absent_id_is_generated(self, client) -> None:
        """Abuse case 2. A caller that sends nothing — a monitor, curl, an old
        client — must not break, and must still be traceable."""
        response = client.get("/healthz")

        assert response.headers[REQUEST_ID_HEADER]

    @pytest.mark.parametrize(
        "hostile",
        [
            "abc\ndef",
            "abc\r\nWARNING fake log line",
            "abc def",
            '{"json":"injection"}',
            "x" * (MAX_REQUEST_ID_LENGTH + 1),
            "<script>alert(1)</script>",
        ],
    )
    def test_a_hostile_id_is_replaced_not_echoed(self, client, hostile: str) -> None:
        """Abuse case 1. The value reaches log aggregation, so a newline in it
        is a forged log entry in any handler that is not strictly JSON."""
        response = client.get("/healthz", headers={REQUEST_ID_HEADER: hostile})

        assert response.headers[REQUEST_ID_HEADER] != hostile

    def test_and_the_replacement_is_usable(self, client) -> None:
        """The twin. Replacing a hostile id with an empty string would satisfy
        the test above and leave the request untraceable."""
        response = client.get("/healthz", headers={REQUEST_ID_HEADER: "bad\nvalue"})

        assert len(response.headers[REQUEST_ID_HEADER]) > 8


class TestTheQueueHop:
    """The hop M14 added.

    Driven against the signal handlers directly rather than through a task.
    `.apply()` runs a task locally and builds no message, so it cannot carry a
    header — and `.delay()` would need a live broker, which a unit suite should
    not require. What these cover is the contract this project owns: what the
    publisher stamps, the consumer adopts, sanitises, and clears.
    """

    def test_the_two_handlers_round_trip_an_id(self) -> None:
        """The contract this project owns: what `before_task_publish` stamps,
        `task_prerun` adopts.

        Driven handler-to-handler rather than through `.apply()`, and that is a
        correction — the first version passed `headers=` to `.apply()` and
        asserted the task saw them. It does not: `.apply()` runs the task
        locally and builds no message, so `task.request` has no `request_id`
        attribute at all. The test failed, and it was the test that was wrong.

        What `.apply()` cannot cover — that Celery delivers a custom message
        header onto `task.request` in a real worker — is Celery's behaviour
        rather than ours, and is verified end to end against a live broker
        rather than asserted here. See the commit for M14 T2.
        """
        from config.celery import _adopt_request_id, _carry_request_id

        request_id_var.set("req-from-the-browser")
        headers: dict[str, str] = {}
        _carry_request_id(headers=headers)

        # What the worker would see, built from the message the publisher sent.
        class DeliveredRequest:
            request_id = headers["request_id"]

        class DeliveredTask:
            request = DeliveredRequest()

        request_id_var.set("")
        _adopt_request_id(task=DeliveredTask())

        assert request_id_var.get() == "req-from-the-browser"

    def test_a_task_with_no_inbound_id_gets_its_own(self) -> None:
        """Work published outside a request — a management command, a periodic
        sweep — is still traceable, and honestly says it did not come from a
        request rather than borrowing one."""
        from config.celery import _adopt_request_id

        class BareRequest:
            pass

        class BareTask:
            request = BareRequest()

        request_id_var.set("")
        _adopt_request_id(task=BareTask())

        minted = request_id_var.get()

        assert minted
        assert len(minted) > 8

    def test_a_hostile_inbound_id_is_not_adopted(self) -> None:
        """Abuse case 1 at the queue boundary. Trusting a value because it came
        from our own broker is an assumption about deployment, not about code —
        and the value still ends up in a log line either way."""
        from config.celery import _adopt_request_id

        class FakeRequest:
            request_id = "queued\nWARNING forged"

        class FakeTask:
            request = FakeRequest()

        _adopt_request_id(task=FakeTask())

        assert request_id_var.get() != "queued\nWARNING forged"
        assert "\n" not in request_id_var.get()

    def test_the_id_does_not_leak_into_the_next_task(self) -> None:
        """A worker process is long-lived. Without the `task_postrun` handler
        the next task's log lines carry the previous task's id, which is worse
        than no id at all — it is a wrong one."""
        from config.celery import _clear_request_id

        request_id_var.set("previous-task")
        _clear_request_id()

        assert request_id_var.get() == ""

    def test_publishing_stamps_the_current_id_onto_the_message(self) -> None:
        from config.celery import _carry_request_id

        headers: dict[str, str] = {}
        request_id_var.set("req-abc")
        _carry_request_id(headers=headers)

        assert headers["request_id"] == "req-abc"

    def test_publishing_outside_a_request_stamps_nothing(self) -> None:
        """Rather than stamping an empty string, which the consumer would then
        have to tell apart from a real one."""
        from config.celery import _carry_request_id

        headers: dict[str, str] = {}
        request_id_var.set("")
        _carry_request_id(headers=headers)

        assert headers == {}


class TestTheLogFilter:
    def test_a_record_carries_the_current_id(self) -> None:
        from apps.core.logging import RequestIDFilter

        request_id_var.set("req-in-flight")
        record = logging.LogRecord("t", logging.INFO, "p", 1, "m", (), None)
        RequestIDFilter().filter(record)

        assert record.request_id == "req-in-flight"

    def test_and_shows_a_dash_when_nothing_is_in_flight(self) -> None:
        """One place decides what "no request" looks like. The Celery handler
        sets the variable to empty and lets this render it."""
        from apps.core.logging import RequestIDFilter

        request_id_var.set("")
        record = logging.LogRecord("t", logging.INFO, "p", 1, "m", (), None)
        RequestIDFilter().filter(record)

        assert record.request_id == NO_REQUEST


class TestTheFrontendSendsOne:
    """Structural, and it is the hop that was missing.

    **Superseded by `frontend/src/lib/api/client.test.ts` as of M15 T2**, and
    kept rather than deleted because the two check different things. These read
    the file as text, so they pass if the header appears in a comment and pass
    if it is set and then removed two lines later. The Vitest suite exercises
    the real `request` function against a stubbed `fetch` and asserts what a
    server would actually receive.

    What survives here is the cross-repository claim: that the *backend's* idea
    of this contract still matches a file in `frontend/`. A frontend test cannot
    fail when somebody deletes the client entirely; this can.
    """

    @staticmethod
    def _client_source() -> str:
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "api" / "client.ts"
        ).read_text(encoding="utf-8")

    def test_the_api_client_sets_the_header(self) -> None:
        source = self._client_source()

        assert "X-Request-ID" in source

    def test_it_sets_it_in_the_shared_request_function(self) -> None:
        """Not in one call site. Every request goes through `request<T>`, and
        setting it anywhere else would cover whichever calls somebody
        remembered."""
        source = self._client_source()
        shared = source[source.index("async function request<T>") :]

        assert "X-Request-ID" in shared or "REQUEST_ID_HEADER" in shared

    def test_a_caller_supplied_id_is_not_overwritten(self) -> None:
        """A caller that already has an id is continuing a trace rather than
        starting one."""
        source = self._client_source()

        assert "has(REQUEST_ID_HEADER)" in source


class TestTheWorkerUsesOurLogging:
    """The gap that made the third hop invisible even when it worked.

    Celery replaces the root logger's handlers on startup by default, which
    undoes Django's `LOGGING` inside the worker: plain text, no JSON formatter,
    and — the part that matters — no `RequestIDFilter`. §3.7 asks for structured
    JSON carrying the id, and with the hijack in place the worker satisfies
    neither half.

    Found by end-to-end verification in M14 T2, not by these tests: the id was
    provably in the queued message and absent from every worker log line. A
    unit test cannot see that, which is why the chain was walked against a live
    broker before it was believed.
    """

    def test_celery_does_not_hijack_the_root_logger(self, settings) -> None:
        assert settings.CELERY_WORKER_HIJACK_ROOT_LOGGER is False

    def test_the_request_id_filter_is_configured(self, settings) -> None:
        """The twin. Leaving the hijack off buys nothing if the filter that
        attaches the id is not wired into the handler."""
        filters = settings.LOGGING.get("filters", {})

        assert any("RequestID" in str(spec) for spec in filters.values()), filters
