"""The CSP violation report endpoint. M13 T2, closing M12's handover.

M12 shipped the policy report-only with nowhere to report to, because
inventing an endpoint would have put a fabricated URL in the header of every
response. This is that endpoint, and the thing worth keeping in mind while
reading these tests is what it is:

**an unauthenticated POST body from anyone on the internet.**

Browsers send violation reports with no credentials and no CSRF token, so the
endpoint cannot require either — which means every property that keeps it from
being a free write into our infrastructure has to be tested. It is bounded, it
stores nothing, it logs no more than it needs, and it answers identically to
everything so that probing it reveals nothing.
"""

from __future__ import annotations

import json

import pytest

URL = "/csp-report/"

pytestmark = pytest.mark.django_db

VALID_REPORT = {
    "csp-report": {
        "document-uri": "https://lingua.example/lesson/intro/",
        "violated-directive": "script-src 'self'",
        "effective-directive": "script-src",
        "blocked-uri": "https://evil.example/x.js",
        "original-policy": "default-src 'self'; script-src 'self'",
    }
}


def _post(client, payload, content_type="application/csp-report"):
    body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    return client.post(URL, body, content_type=content_type)


class TestItAcceptsAReport:
    def test_a_browser_report_is_accepted(self, client) -> None:
        assert _post(client, VALID_REPORT).status_code == 204

    def test_no_authentication_is_required(self, client) -> None:
        """It cannot be. Browsers send these with no credentials, so requiring
        any would mean receiving nothing — which is indistinguishable from a
        policy with no violations."""
        assert _post(client, VALID_REPORT).status_code == 204

    def test_no_csrf_token_is_required(self) -> None:
        """Same reason, and worth its own test because CSRF exemption is
        normally a smell. Here the alternative is an endpoint that receives
        nothing.

        A client with `enforce_csrf_checks=True`, because pytest-django's
        default `client` does not check CSRF at all — asserting against that
        one would pass whether the view were exempt or not.
        """
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)

        assert _post(strict, VALID_REPORT).status_code == 204

    def test_the_newer_reporting_api_shape_is_accepted_too(self, client) -> None:
        """Not every browser wraps the body in `csp-report`. A bare object is
        read as the report itself rather than dropped."""
        response = _post(client, VALID_REPORT["csp-report"])

        assert response.status_code == 204


class TestItLogsWhatMatters:
    def test_the_violated_directive_is_logged(self, client, caplog) -> None:
        with caplog.at_level("INFO", logger="apps.core.csp"):
            _post(client, VALID_REPORT)

        assert "csp_violation" in caplog.text

    def test_the_blocked_uri_is_logged(self, client, caplog) -> None:
        """The single most useful field: it names what the page tried to load."""
        with caplog.at_level("INFO", logger="apps.core.csp"):
            _post(client, VALID_REPORT)

        record = next(r for r in caplog.records if getattr(r, "event", "") == "csp_violation")

        assert record.blocked_uri == "https://evil.example/x.js"

    def test_the_original_policy_is_not_logged(self, client, caplog) -> None:
        """It is the entire policy on every single report — the same hundreds
        of bytes repeated, telling us nothing we do not already know, on an
        endpoint anyone can call.

        Asserted against the record's **attributes**, not `caplog.text`. The
        first version checked the text and passed even when the whole report
        body was logged, because `extra=` fields never appear there — a test
        that could not fail, guarding the field most worth not logging.
        """
        with caplog.at_level("INFO", logger="apps.core.csp"):
            _post(client, VALID_REPORT)

        record = next(r for r in caplog.records if getattr(r, "event", "") == "csp_violation")
        logged = " ".join(str(value) for value in record.__dict__.values())

        assert "original-policy" not in logged
        assert "default-src" not in logged

    def test_only_the_declared_fields_are_logged(self, client, caplog) -> None:
        """The positive form of the test above, and the one that survives a
        browser adding a field to the report rather than us adding one."""
        from apps.core.views import REPORTED_FIELDS

        with caplog.at_level("INFO", logger="apps.core.csp"):
            _post(client, VALID_REPORT)

        record = next(r for r in caplog.records if getattr(r, "event", "") == "csp_violation")
        expected = {field.replace("-", "_") for field in REPORTED_FIELDS}
        from_report = {
            key for key in record.__dict__ if key.replace("_", "-") in VALID_REPORT["csp-report"]
        }

        assert from_report == expected

    def test_a_long_field_is_truncated(self, client, caplog) -> None:
        """A URL can carry a token in its query string, and the sender chooses
        the URL. Truncated hard rather than parsed — a parser here would be one
        more thing accepting hostile input."""
        from apps.core.views import MAX_FIELD_LENGTH

        report = {"csp-report": {**VALID_REPORT["csp-report"], "blocked-uri": "x" * 5_000}}

        with caplog.at_level("INFO", logger="apps.core.csp"):
            _post(client, report)

        record = next(r for r in caplog.records if getattr(r, "event", "") == "csp_violation")

        assert len(record.blocked_uri) <= MAX_FIELD_LENGTH


class TestItCannotBeUsedAgainstUs:
    def test_an_oversized_body_is_dropped(self, client, caplog) -> None:
        """Bounded because the sender is anonymous: without a limit this is a
        way to write an arbitrarily large log line, for free, from anywhere."""
        from apps.core.views import MAX_REPORT_BYTES

        oversized = {"csp-report": {"blocked-uri": "x" * (MAX_REPORT_BYTES + 1_000)}}

        with caplog.at_level("INFO", logger="apps.core.csp"):
            response = _post(client, oversized)

        assert response.status_code == 204
        assert "csp_violation" not in caplog.text

    def test_malformed_json_is_not_an_error(self, client, caplog) -> None:
        """Malformed input from an anonymous source is not an incident. Logging
        it at error level would make the endpoint a way to fill an alert
        channel."""
        with caplog.at_level("WARNING"):
            response = _post(client, "{not json", content_type="application/csp-report")

        assert response.status_code == 204
        assert caplog.records == []

    def test_a_non_object_report_is_dropped(self, client, caplog) -> None:
        with caplog.at_level("INFO", logger="apps.core.csp"):
            response = _post(client, {"csp-report": "a string, not an object"})

        assert response.status_code == 204
        assert "csp_violation" not in caplog.text

    def test_every_outcome_answers_identically(self, client) -> None:
        """Valid, oversized, malformed and hostile all return 204. A browser
        does nothing with the status, and a distinguishable rejection tells
        somebody probing exactly where the limits are."""
        bodies = [
            json.dumps(VALID_REPORT),
            json.dumps({"csp-report": {"blocked-uri": "x" * 20_000}}),
            "{not json",
            json.dumps({"csp-report": []}),
            "",
        ]

        statuses = {_post(client, body).status_code for body in bodies}

        assert statuses == {204}

    def test_it_stores_nothing(self, client) -> None:
        """ADR-020 §8's reasoning, and it holds harder here: a table written by
        anonymous callers is a way for anyone to write unbounded rows into our
        database."""
        from django.apps import apps as django_apps

        before = {
            model: model.objects.count()
            for model in django_apps.get_app_config("core").get_models()
        }

        _post(client, VALID_REPORT)

        for model, count in before.items():
            assert model.objects.count() == count, model.__name__

    def test_a_get_is_refused(self, client) -> None:
        """Nothing reads reports back. A readable endpoint would be a way to
        find out what our policy blocks."""
        assert client.get(URL).status_code == 405


class TestItIsNotPartOfTheApi:
    def test_it_is_absent_from_the_openapi_schema(self, client) -> None:
        """A published endpoint that accepts anonymous POSTs is an invitation.
        It is also not part of the product API — no client calls it."""
        schema = client.get("/api/v1/schema/").content.decode()

        assert "csp-report" not in schema

    def test_it_lives_outside_the_versioned_api(self) -> None:
        from django.urls import reverse

        assert reverse("csp-report") == URL
        assert not URL.startswith("/api/")
