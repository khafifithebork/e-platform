"""Every environment variable the code reads must be documented.

An undocumented variable is not a tidiness problem, it is a deploy failure:
``base.py`` reads several without defaults, so a missing one takes the process
down at import. This test fails the moment code starts reading a variable that
``.env.example`` does not mention.

CLAUDE.md section 6 requires ``.env.example`` to document names only, so this
checks for the presence of each name and never for a value.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = BACKEND_ROOT / ".env.example"

# django-environ:  env("NAME")  env.bool("NAME")  env.int("NAME")  env.db("NAME")
_DJANGO_ENV_READ = re.compile(r"\benv(?:\.\w+)?\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")
# gunicorn.conf.py deliberately avoids django-environ.
_OS_ENVIRON_READ = re.compile(r"\bos\.environ\.get\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")

# Read by Django itself before any of our code runs, so it never appears in a
# settings module but must still be documented.
_IMPLICIT = {"DJANGO_SETTINGS_MODULE"}


def _sources() -> list[Path]:
    return [
        *(BACKEND_ROOT / "config" / "settings").glob("*.py"),
        BACKEND_ROOT / "gunicorn.conf.py",
    ]


def _variables_read_by_the_code() -> set[str]:
    names: set[str] = set()
    for path in _sources():
        source = path.read_text(encoding="utf-8")
        names.update(_DJANGO_ENV_READ.findall(source))
        names.update(_OS_ENVIRON_READ.findall(source))
    return names


def _variables_documented() -> set[str]:
    documented: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        documented.add(stripped.split("=", 1)[0].strip())
    return documented


class TestEnvExample:
    def test_file_exists(self) -> None:
        assert ENV_EXAMPLE.exists()

    def test_documents_every_variable_the_code_reads(self) -> None:
        undocumented = (_variables_read_by_the_code() | _IMPLICIT) - _variables_documented()

        assert not undocumented, f"missing from .env.example: {sorted(undocumented)}"

    def test_documents_no_variable_the_code_does_not_read(self) -> None:
        """A stale entry is misleading in the other direction — it invites
        someone to set something that has no effect."""
        stale = _variables_documented() - (_variables_read_by_the_code() | _IMPLICIT)

        assert not stale, f"documented but never read: {sorted(stale)}"

    def test_contains_no_values(self) -> None:
        """CLAUDE.md section 6: names only. A real value here is how a secret
        reaches version control."""
        with_values = [
            line.strip()
            for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
            if "=" in line and not line.strip().startswith("#") and line.split("=", 1)[1].strip()
        ]

        assert not with_values, f"lines carry values: {with_values}"
