"""Error reporting: what it is configured to do, and what it refuses to do.

**None of this proves an event reaches Sentry.** No DSN exists in this
repository, so nothing here observes delivery — these tests cover
configuration, refusal and scrubbing, which are the parts that live in code.
Delivery is confirmed once somebody provisions the account, and until then this
is ADR-006's inert control by construction rather than by oversight. The M14
spec says so in T5's "honest limit", and ADR-027 §3 repeats it.

The vendor boundary is monkeypatched in one place — ``sentry_sdk.init`` — which
is the opposite of the practice CLAUDE.md §6 forbids. That rule is about
mocking *our own* service layer and asserting it was called; here the assertion
is about the options we hand to a third party, and calling the real ``init``
would install a live client for the rest of the session.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.conf import settings

from apps.core.logging import request_id_var
from apps.core.observability import (
    _MAX_DEPTH,
    REDACTED,
    _before_send,
    initialise_error_reporting,
    redact_addresses,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class TestItDoesNothingWithoutADsn:
    def test_an_empty_dsn_reports_that_it_did_not_initialise(self) -> None:
        """The ordinary state of every developer machine and of CI. A missing
        DSN must not raise: `manage.py check` would then fail for everyone, to
        protect a concern that only exists in production."""
        assert initialise_error_reporting(dsn="", environment="test") is False

    def test_it_does_not_touch_the_sdk_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The twin. A function that called `init(dsn="")` and returned False
        would satisfy the test above while installing a client."""
        calls: list[dict] = []
        monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))

        initialise_error_reporting(dsn="", environment="test")

        assert calls == []

    def test_the_running_test_suite_has_reporting_off(self) -> None:
        """Not a tautology: `test.py` reads `backend/.env` through `read_env`,
        so a developer with a real DSN there would otherwise report every
        deliberately-raised exception in this suite to a live project."""
        assert settings.SENTRY_ENABLED is False

    def test_the_test_settings_overwrite_the_dsn_rather_than_defaulting_it(self) -> None:
        """`setdefault` would leave a DSN from `.env` in place, and the suite
        has over 1400 tests against a monthly quota of 5k errors. Read from the
        syntax tree rather than the text, so a comment mentioning the line
        cannot satisfy it — the mistake this codebase has made four times."""
        tree = ast.parse((BACKEND_ROOT / "config" / "settings" / "test.py").read_text("utf-8"))

        overwrites = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "environ"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "SENTRY_DSN"
        ]

        assert len(overwrites) == 1


class TestTheOptionsItHandsToTheVendor:
    @staticmethod
    def _options(monkeypatch: pytest.MonkeyPatch, **overrides) -> dict:
        captured: dict = {}
        monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: captured.update(kwargs))
        initialise_error_reporting(
            **{"dsn": "https://k@example.invalid/1", "environment": "staging", **overrides}
        )
        return captured

    def test_personal_data_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With this off the SDK attaches no Django user object, no request
        body and no headers. Passed explicitly although the SDK currently
        treats `None` the same way: a default is a fact about a version, and
        this is a line a test can assert."""
        assert self._options(monkeypatch)["send_default_pii"] is False

    def test_tracing_is_off_unless_asked_for(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tracing bills a quota separate from errors. Whether we want it is
        M14 T6's question; turning it on by accident is how a free tier is
        spent before anyone looks at it."""
        assert self._options(monkeypatch)["traces_sample_rate"] == 0.0

    def test_an_empty_release_becomes_none_rather_than_an_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty string is a release named "" in the Sentry UI, which is
        worse than no release at all: issues group under a version that does
        not exist."""
        assert self._options(monkeypatch, release="")["release"] is None

    def test_the_scrubber_is_wired_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without this the scrubber tests below pass while nothing calls it —
        they invoke `_before_send` directly, so deleting the `before_send=`
        argument would leave every one of them green and every event
        unscrubbed. The exact failure this suite has shipped four times."""
        assert self._options(monkeypatch)["before_send"] is _before_send

    def test_a_malformed_dsn_fails_loudly(self) -> None:
        """**A deliberate choice, not the absence of one.** A DSN typo could
        either crash the process or silently disable reporting, and silence is
        the worse failure: it is exactly ADR-006's inert control, and it would
        be discovered during the incident it was meant to report.

        Crashing is caught where it is introduced — the deploy pipeline polls
        `/healthz` before it proceeds — so the blast radius is a failed deploy.
        This pins the SDK's own behaviour so a future version that starts
        swallowing bad DSNs is noticed here."""
        with pytest.raises(Exception, match="scheme"):
            initialise_error_reporting(dsn="not-a-dsn", environment="test")


class TestAddressesAreRemovedBeforeAnythingIsSent:
    """The SDK's own scrubber is **key**-based — it removes values under names
    like `password` — and `email` is not in its denylist. Verified against the
    installed package rather than assumed. More to the point, a key-based
    scrubber cannot reach an address inside an exception *message*, and that is
    the shape this codebase produces: account and notification errors quote the
    address they were handed.
    """

    def test_an_address_in_an_exception_message_is_removed(self) -> None:
        assert redact_addresses("user alice@example.com already exists") == (
            f"user {REDACTED} already exists"
        )

    def test_it_reaches_into_nested_structures(self) -> None:
        """An event is a tree — `exception.values[].stacktrace.frames[].vars` —
        so a scrubber that only looked at the top level would look like it
        worked and miss every local variable."""
        event = {"extra": {"context": ["queued for", ("retry", "eve@mail.org")]}}

        assert redact_addresses(event) == {
            "extra": {"context": ["queued for", ("retry", REDACTED)]}
        }

    def test_it_leaves_text_that_is_not_an_address_alone(self) -> None:
        """The twin, and the one that matters. A scrubber that redacted
        everything would pass both tests above and make every stack trace
        useless — which nobody would notice until they needed one."""
        for untouched in ("path/to/file.py line 40", "5 > 3 and a@b", "@decorator"):
            assert redact_addresses(untouched) == untouched

    def test_it_stops_descending_past_the_limit_and_this_is_the_cost(self) -> None:
        """**The cap has a price and this test is where it is written down:**
        an address nested deeper than `_MAX_DEPTH` is not redacted.

        That is an accepted trade, not an oversight. The alternative is a
        `RecursionError` raised inside `before_send`, which drops the event
        entirely — the one failure mode an error reporter must not have — and
        real events are nowhere near this deep.

        Asserted at the boundary rather than by counting stack frames, because
        the depth an interpreter tolerates varies and a test that passes on a
        developer machine for that reason is not a test."""
        buried: object = "leaf@example.com"
        for _ in range(_MAX_DEPTH + 2):
            buried = {"next": buried}

        assert "leaf@example.com" in str(redact_addresses(buried))

    def test_it_survives_a_pathologically_deep_event(self) -> None:
        """The twin, and the reason the cap exists. Without it this raises —
        provoked at 1000 levels, so 2000 leaves margin for a CI interpreter
        with a different recursion limit."""
        deep: object = "leaf@example.com"
        for _ in range(2000):
            deep = {"next": deep}

        redact_addresses(deep)  # must not raise


class TestTheRequestIdReachesSentry:
    """M14 T2 propagated the id from the browser through Django into Celery.
    Without this tag a Sentry issue and the log lines describing the same
    request can only be joined by timestamp.
    """

    def test_the_id_in_flight_becomes_a_tag(self) -> None:
        token = request_id_var.set("abc-123")
        try:
            assert _before_send({}, {})["tags"]["request_id"] == "abc-123"
        finally:
            request_id_var.reset(token)

    def test_existing_tags_survive(self) -> None:
        token = request_id_var.set("abc-123")
        try:
            tagged = _before_send({"tags": {"kept": "yes"}}, {})
        finally:
            request_id_var.reset(token)

        assert tagged["tags"] == {"kept": "yes", "request_id": "abc-123"}

    def test_nothing_is_tagged_when_no_request_is_in_flight(self) -> None:
        """Startup, a management command, a worker between tasks. An empty tag
        is worse than none: it is a filterable value that matches everything
        that happened outside a request."""
        assert "tags" not in _before_send({}, {})

    def test_the_event_is_scrubbed_on_the_way_through(self) -> None:
        """`before_send` is the only hook that runs on every event, so the
        scrubber being wired into it is the thing that makes it a control
        rather than a function nobody calls."""
        scrubbed = _before_send({"message": "failed for bob@example.com"}, {})

        assert "bob@example.com" not in scrubbed["message"]


class TestTheVendorIsNamedInOneModule:
    """Invariant 4's purpose, kept without an adapter.

    Sentry has no call site — it installs itself at boot and our code never
    invokes it — so a `providers/sentry.py` would wrap nothing. What the
    invariant protects is that the vendor can be removed or replaced by editing
    one file, and that is what this asserts. ADR-027 §1.
    """

    SEAM = "apps/core/observability.py"

    @staticmethod
    def _product_modules() -> list[Path]:
        """Product code only. Tests may reference the vendor to monkeypatch it,
        and a guard that forbade that would forbid testing the seam."""
        return [
            path
            for directory in ("apps", "config")
            for path in (BACKEND_ROOT / directory).rglob("*.py")
            if "migrations" not in path.parts
        ]

    @staticmethod
    def _names_the_vendor(source: str) -> bool:
        """Parsed, not grepped. Every previous version of this check in this
        repository matched its own explanatory comment; the syntax tree does
        not contain comments, so it cannot."""
        return any(
            (
                isinstance(node, ast.Import)
                and any(a.name.split(".")[0] == "sentry_sdk" for a in node.names)
            )
            or (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "sentry_sdk"
            )
            for node in ast.walk(ast.parse(source))
        )

    def test_exactly_one_module_imports_the_sdk(self) -> None:
        importers = sorted(
            path.relative_to(BACKEND_ROOT).as_posix()
            for path in self._product_modules()
            if self._names_the_vendor(path.read_text(encoding="utf-8"))
        )

        assert importers == [self.SEAM]

    def test_the_guard_would_catch_a_second_importer(self) -> None:
        """The twin. A detector that matched nothing would pass the test above
        by finding zero importers — except that one asserts an exact list, so
        this checks the other half: that a real second import is detected."""
        assert self._names_the_vendor("import sentry_sdk\n")
        assert self._names_the_vendor("from sentry_sdk import capture_exception\n")
        assert not self._names_the_vendor("# import sentry_sdk\nimport json\n")
