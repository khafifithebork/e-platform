"""The metrics endpoint, and everything it refuses. M14 T6.

An unauthenticated `/metrics` publishes queue depth and backlog size — a
description of how loaded this system is and when it is weakest. So most of
this file is about refusals, and every one of them was provoked before it was
believed (ADR-006).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

TOKEN = "a-token-that-exists-only-in-this-test"


def _get(client, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.get(reverse("metrics"), headers=headers)


class TestItDoesNotExistUntilConfigured:
    def test_no_token_configured_answers_404(self, client, settings) -> None:
        """The state of this repository: nothing scrapes it, so the feature is
        off. 404 rather than 403 because there is genuinely nothing here —
        the endpoint is a capability that has not been turned on."""
        settings.METRICS_TOKEN = ""

        assert _get(client, TOKEN).status_code == 404

    def test_it_stays_404_even_with_a_correct_looking_request(self, client, settings) -> None:
        """The twin. An unconfigured endpoint must not become reachable by
        presenting an empty token against an empty setting — which
        `compare_digest("", "")` would happily accept."""
        settings.METRICS_TOKEN = ""

        assert _get(client, "").status_code == 404
        assert _get(client).status_code == 404


class TestWhatItRefusesOnceConfigured:
    @pytest.fixture(autouse=True)
    def _configured(self, settings):
        settings.METRICS_TOKEN = TOKEN

    def test_no_authorization_header_is_refused(self, client) -> None:
        assert _get(client).status_code == 403

    def test_a_wrong_token_is_refused(self, client) -> None:
        assert _get(client, "not-the-token").status_code == 403

    def test_a_token_without_the_bearer_scheme_is_refused(self, client) -> None:
        """A scraper configured with the raw token in the header is a
        misconfiguration, and accepting it would mean the scheme is decoration."""
        response = client.get(reverse("metrics"), headers={"Authorization": TOKEN})

        assert response.status_code == 403

    def test_a_prefix_of_the_token_is_refused(self, client) -> None:
        """The shape a timing attack converges on. It is refused for the
        ordinary reason too, but this is the case worth naming."""
        assert _get(client, TOKEN[:-1]).status_code == 403

    def test_the_refusal_body_says_nothing(self, client) -> None:
        """No metric names, no configuration, no hint about the token. A
        refusal that describes what it wanted is a refusal that helps."""
        body = _get(client, "wrong").content.decode()

        assert "eplatform" not in body
        assert TOKEN not in body

    def test_writes_are_not_allowed(self, client) -> None:
        """`require_safe`. A POST to a read-only endpoint should be refused by
        the routing layer rather than by the view happening to ignore it."""
        assert (
            client.post(
                reverse("metrics"), headers={"Authorization": f"Bearer {TOKEN}"}
            ).status_code
            == 405
        )


class TestWhatItServes:
    @pytest.fixture(autouse=True)
    def _configured(self, settings):
        settings.METRICS_TOKEN = TOKEN

    def test_a_correct_token_gets_the_exposition_format(self, client) -> None:
        response = _get(client, TOKEN)

        assert response.status_code == 200
        assert response.content.decode().startswith("# HELP eplatform_")

    def test_it_declares_the_exposition_format_version(self, client) -> None:
        """Scrapers content-negotiate on it, and some guess when it is absent."""
        assert "version=0.0.4" in _get(client, TOKEN)["Content-Type"]

    def test_it_is_never_cached(self, client) -> None:
        """A cached scrape is a lie with a timestamp on it."""
        assert _get(client, TOKEN)["Cache-Control"] == "no-store"

    def test_it_carries_no_identifiers(self, client, django_user_model) -> None:
        """M14 §6 case 6, at the surface rather than only in the collector. The
        body is checked against a real user and course that exist while it is
        served, so a future metric that added a label would fail here."""
        django_user_model.objects.create_user(
            email="metrics-leak@example.test", password="irrelevant-to-this-test"
        )
        body = _get(client, TOKEN).content.decode()

        assert "metrics-leak@example.test" not in body
        assert "{" not in body

    def test_it_answers_without_a_session(self, client) -> None:
        """A scraper holds no account and cannot log in. This is the failure
        `healthz` records in its own docstring: a DRF view here would default
        to IsAuthenticated and answer 403 forever, and the endpoint would look
        like it was working."""
        assert "sessionid" not in client.cookies
        assert _get(client, TOKEN).status_code == 200


class TestItIsNotPartOfTheProductApi:
    def test_it_is_absent_from_the_openapi_schema(self, client, settings) -> None:
        """Infrastructure, not product. A scraper endpoint in the published
        schema would generate a frontend client method for something no browser
        may call — and invariant 16 generates those types automatically."""
        settings.METRICS_TOKEN = TOKEN

        schema = client.get(reverse("schema")).content.decode()

        assert "/metrics" not in schema


class TestTheComparisonIsConstantTime:
    """**No behavioural test can catch this one.**

    Replacing `secrets.compare_digest` with `==` changes nothing observable:
    same status codes, same bodies, every test above still green. What changes
    is that the token leaks its prefix to anyone who can measure a few thousand
    requests, and the endpoint it guards reads operational data.

    So it is asserted structurally, from the syntax tree rather than the text —
    a comment mentioning `compare_digest` must not satisfy it. Same shape as
    M14 T5's vendor-seam guard, and for the same reason.
    """

    @staticmethod
    def _metrics_function() -> ast.FunctionDef:
        source = (Path(__file__).resolve().parents[2] / "apps" / "core" / "views.py").read_text(
            encoding="utf-8"
        )
        return next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "metrics"
        )

    def test_the_token_is_compared_with_compare_digest(self) -> None:
        calls = {
            node.func.attr
            for node in ast.walk(self._metrics_function())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        assert "compare_digest" in calls

    def test_the_token_is_never_compared_with_an_operator(self) -> None:
        """The twin. Adding `compare_digest` somewhere while leaving an `==`
        on the token would satisfy the test above and keep the leak."""
        comparisons = [
            node
            for node in ast.walk(self._metrics_function())
            if isinstance(node, ast.Compare)
            and any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops)
        ]

        assert comparisons == []
