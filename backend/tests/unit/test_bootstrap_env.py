"""The environment bootstrap.

Idempotency is the property that matters. Regenerating POSTGRES_PASSWORD
against a Postgres volume that was initialised with the old one produces an
authentication failure that looks like a credentials bug and is not — the
password only takes effect when the data directory is first created.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "bootstrap_env.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("bootstrap_env", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParsing:
    def test_reads_key_value_pairs(self) -> None:
        parsed = _load().parse_env("A=1\nB=two\n")

        assert parsed == {"A": "1", "B": "two"}

    def test_ignores_comments_and_blanks(self) -> None:
        parsed = _load().parse_env("# a comment\n\nA=1\n")

        assert parsed == {"A": "1"}

    def test_keeps_equals_signs_inside_a_value(self) -> None:
        """Base64 secrets and connection URLs both contain them."""
        parsed = _load().parse_env("URL=postgres://u:p==@h:5432/d\n")

        assert parsed["URL"] == "postgres://u:p==@h:5432/d"


class TestIdempotency:
    def test_nothing_missing_when_both_keys_are_present(self) -> None:
        module = _load()

        assert module.missing_keys({"DJANGO_SECRET_KEY": "x", "POSTGRES_PASSWORD": "y"}) == []

    def test_an_empty_value_counts_as_missing(self) -> None:
        """A key present but blank is a half-written file, not a decision."""
        module = _load()

        assert "POSTGRES_PASSWORD" in module.missing_keys(
            {"DJANGO_SECRET_KEY": "x", "POSTGRES_PASSWORD": ""}
        )


class TestDerivedBackendEnvironment:
    def _built(self, **overrides: str) -> dict[str, str]:
        module = _load()
        compose = {
            "DJANGO_SECRET_KEY": "generated-key",
            "POSTGRES_PASSWORD": "generated-password",
            **overrides,
        }
        return module.build_backend_env(compose)

    def test_supplies_everything_local_settings_require(self) -> None:
        """base.py reads these without defaults, so a missing one stops the
        process at import."""
        built = self._built()

        for required in ("DJANGO_SECRET_KEY", "DATABASE_URL", "REDIS_URL", "REDIS_CACHE_URL"):
            assert built[required]

    def test_points_at_local_settings(self) -> None:
        assert self._built()["DJANGO_SETTINGS_MODULE"] == "config.settings.local"

    def test_uses_the_published_host_port(self) -> None:
        """Compose reaches postgres over its own network; a developer running
        pytest on the host reaches whatever port was published — which is
        overridable because something else may already hold the default."""
        built = self._built(POSTGRES_PORT="5433")

        assert "127.0.0.1:5433" in built["DATABASE_URL"]

    def test_falls_back_to_the_conventional_port(self) -> None:
        assert "127.0.0.1:5432" in self._built()["DATABASE_URL"]

    def test_carries_the_generated_password_through(self) -> None:
        assert "generated-password" in self._built()["DATABASE_URL"]

    def test_cache_and_broker_use_different_redis_databases(self) -> None:
        """Sharing one means a cache flush deletes queued tasks."""
        built = self._built()

        assert built["REDIS_URL"] != built["REDIS_CACHE_URL"]
        assert built["REDIS_URL"].endswith("/0")
        assert built["REDIS_CACHE_URL"].endswith("/1")
