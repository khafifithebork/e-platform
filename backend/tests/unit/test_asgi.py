"""Contracts for the ASGI entrypoint and the Gunicorn configuration.

Invariant 12: this project runs under ASGI so that Server-Sent Events and, if
they are ever needed, Channels become configuration rather than a migration
(ADR-002 section 7.5). These tests exist to make a silent revert to WSGI fail
loudly.

A note on what is *not* tested here. Gunicorn is Unix-only — it imports fcntl —
so neither gunicorn nor uvicorn_worker can be imported on Windows, where this
is developed. The configuration file is therefore written with no gunicorn
imports, which lets these tests read its values on any platform. That the
worker class actually resolves is verified when the container runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GUNICORN_CONF = BACKEND_ROOT / "gunicorn.conf.py"


def _load_gunicorn_config() -> dict[str, Any]:
    """Execute gunicorn.conf.py and return its module namespace.

    Gunicorn itself loads this file by execution, not import, so reading it the
    same way tests what Gunicorn will actually see.
    """
    spec = importlib.util.spec_from_file_location("gunicorn_conf", GUNICORN_CONF)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return vars(module)


class TestAsgiEntrypoint:
    def test_application_is_importable(self) -> None:
        from config.asgi import application

        assert application is not None

    def test_application_is_an_asgi_callable(self) -> None:
        """ASGI applications are callables taking (scope, receive, send)."""
        from config.asgi import application

        assert callable(application)


class TestGunicornConfiguration:
    def test_config_file_exists(self) -> None:
        assert GUNICORN_CONF.exists()

    def test_uses_the_uvicorn_worker_class(self) -> None:
        """The Gunicorn worker class moved out of uvicorn core into the
        uvicorn-worker distribution; uvicorn.workers.UvicornWorker is
        deprecated."""
        assert _load_gunicorn_config()["worker_class"] == "uvicorn_worker.UvicornWorker"

    def test_logs_go_to_stdout_and_stderr(self) -> None:
        """Invariant 5: the app tier is stateless and writes nothing to local
        disk. A dash is Gunicorn's notation for the standard streams."""
        config = _load_gunicorn_config()

        assert config["accesslog"] == "-"
        assert config["errorlog"] == "-"

    def test_config_does_not_import_gunicorn(self) -> None:
        """Importing gunicorn here would make the file unreadable on Windows
        and break the two assertions above."""
        source = GUNICORN_CONF.read_text(encoding="utf-8")

        assert "import gunicorn" not in source
        assert "from gunicorn" not in source
