"""The health endpoint.

Answers exactly one question: is this process alive and serving HTTP?

It deliberately does not answer "can it reach Postgres and Redis". That is a
readiness question, and conflating the two is actively harmful: a liveness
check that fails during a thirty-second database blip invites the orchestrator
to kill and reschedule containers that were about to recover, converting a
brief dependency wobble into a full outage. A readiness endpoint can be added
when there is a deployment that consumes it.

architecture.md 3.7 has uptime monitors polling this every 60 seconds, which
shapes three of the tests below.
"""

from __future__ import annotations

import json


class TestLiveness:
    def test_returns_ok(self, client) -> None:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert json.loads(response.content) == {"status": "ok"}

    def test_touches_no_database(self, client) -> None:
        """The absence of a `django_db` marker on this test *is* the assertion.

        pytest-django blocks database access unless a test asks for it, so if
        the view opened a connection this would fail with "Database access not
        allowed" rather than passing. It also means the suite proves this
        without needing a database at all, which is what lets it run in CI.
        """
        assert client.get("/healthz").status_code == 200

    def test_head_is_supported(self, client) -> None:
        """Uptime monitors commonly use HEAD to avoid transferring a body."""
        assert client.head("/healthz").status_code == 200


class TestNotBehindTheApiStack:
    def test_anonymous_requests_are_allowed(self, client) -> None:
        """DRF defaults to IsAuthenticated (T2). A health check behind that
        would answer 403 forever, and the platform would conclude the service
        was dead."""
        response = client.get("/healthz")

        assert response.status_code == 200

    def test_is_not_rate_limited(self, client) -> None:
        """The anonymous throttle is 60/min per IP. If this endpoint shared
        that bucket, a busy origin would throttle its own health check and the
        platform would kill containers that were serving traffic perfectly
        well. Well past the limit, every response must still be 200.
        """
        statuses = {client.get("/healthz").status_code for _ in range(70)}

        assert statuses == {200}


class TestNotCacheable:
    def test_forbids_caching(self, client) -> None:
        """A cached 200 is worse than no health check: the edge would keep
        answering for a process that has been dead for minutes."""
        response = client.get("/healthz")

        assert "no-store" in response.headers["Cache-Control"]
