"""Refuse to run migrations before a custom User model exists.

Django's first ``migrate`` creates ``auth_user`` from the default model.
Swapping ``AUTH_USER_MODEL`` afterwards is, in the words of
``docs/architecture.md`` section 10, genuinely awful: it means a manual table
rename, a hand-written migration graph rewrite, and every foreign key in the
schema repointed.

The whole cost is avoided by not running ``migrate`` until the custom model is
in place, which is why ``make migrate`` calls this first. The guard disappears
on its own — once ``AUTH_USER_MODEL`` names a project model, this exits zero
and never speaks again.

Exit codes: 0 to proceed, 1 to refuse.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_USER_MODEL = "auth.User"

# Resolved relative to this file rather than the working directory, so the
# guard behaves identically however it is invoked. Running it as
# `python ../scripts/check_custom_user_model.py` puts scripts/ on sys.path,
# not backend/, and `config` would not be importable.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"


def is_custom_user_model(auth_user_model: str) -> bool:
    """True when the project defines its own User model."""
    return auth_user_model != DEFAULT_USER_MODEL


def main() -> int:
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

    import django

    django.setup()

    from django.conf import settings

    if is_custom_user_model(settings.AUTH_USER_MODEL):
        return 0

    sys.stderr.write(
        "\n"
        "Refusing to migrate: AUTH_USER_MODEL is still the Django default.\n"
        "\n"
        "The first migrate creates auth_user, and changing AUTH_USER_MODEL\n"
        "after that is a manual, error-prone schema rewrite. Define the custom\n"
        "User model first (milestone M2), then run this again.\n"
        "\n"
        "If you genuinely mean to migrate against the default model, invoke\n"
        "manage.py migrate directly and know why you are doing it.\n"
        "\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
