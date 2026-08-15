"""The OpenAPI schema, and the guard that keeps the committed copy honest.

Invariant 16: frontend request and response types are generated from this
schema, never hand-written. That only holds if the committed schema actually
matches the code — a stale file generates stale types, and TypeScript then
confidently checks the frontend against an API that no longer exists.

The drift check is a test rather than a CI-only step so it fails on the machine
that caused it, before the push, rather than several minutes later in a
pipeline.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTED_SCHEMA = REPO_ROOT / "docs" / "openapi.yaml"


def _generate() -> bytes:
    """Render the schema exactly as `manage.py spectacular` would."""
    from drf_spectacular.generators import SchemaGenerator
    from drf_spectacular.renderers import OpenApiYamlRenderer

    schema = SchemaGenerator().get_schema(request=None, public=True)
    return OpenApiYamlRenderer().render(schema, renderer_context={})


class TestSchemaEndpoint:
    def test_is_served(self, client) -> None:
        response = client.get("/api/v1/schema/")

        assert response.status_code == 200

    def test_is_readable_without_authentication(self, client) -> None:
        """DRF denies by default (T2), so this needs an explicit exemption.

        Publishing the surface is deliberate. Hiding it would be obscurity
        rather than security — every endpoint is protected by its own
        permission check, and that is what actually holds.
        """
        assert client.get("/api/v1/schema/").status_code == 200

    def test_describes_the_versioned_api(self, client) -> None:
        document = yaml.safe_load(client.get("/api/v1/schema/").content)

        assert document["openapi"].startswith("3.")
        assert document["info"]["title"]

    def test_excludes_infrastructure_endpoints(self, client) -> None:
        """/healthz is a plain Django view outside /api/v1/. It is not part of
        the product API and must not appear in generated client types."""
        document = yaml.safe_load(client.get("/api/v1/schema/").content)

        assert "/healthz" not in (document.get("paths") or {})


class TestCommittedSchemaIsCurrent:
    def test_file_exists(self) -> None:
        assert COMMITTED_SCHEMA.exists(), "run `make schema`"

    def test_matches_the_code(self) -> None:
        """The drift gate.

        If this fails the schema was changed without regenerating: run
        `make schema` and commit the result. Compared as parsed documents
        rather than bytes, so a trailing-newline difference between platforms
        is not reported as an API change.
        """
        committed = yaml.safe_load(COMMITTED_SCHEMA.read_text(encoding="utf-8"))
        generated = yaml.safe_load(_generate())

        assert committed == generated, (
            "docs/openapi.yaml is out of date with the code. "
            "Run `make schema` and commit the result."
        )
