"""The migration guard that keeps M0 from foreclosing M2.

The predicate is separated from the script's main() precisely so both branches
can be tested without a subprocess or a settings reload.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

GUARD = Path(__file__).resolve().parents[3] / "scripts" / "check_custom_user_model.py"


def _load_guard() -> Any:
    spec = importlib.util.spec_from_file_location("check_custom_user_model", GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCustomUserModelPredicate:
    def test_the_django_default_is_rejected(self) -> None:
        assert _load_guard().is_custom_user_model("auth.User") is False

    def test_a_project_model_is_accepted(self) -> None:
        assert _load_guard().is_custom_user_model("accounts.User") is True


class TestGuardHasServedItsPurpose:
    """M2 landed the custom model, so the guard now permits migrations.

    The class this replaced asserted `AUTH_USER_MODEL == "auth.User"` and was
    written to fail exactly once — the moment M2 defined the real model — as a
    reminder to come back here. It did.

    What remains is the assertion that matters going forward: the project must
    never revert to Django's default user model, because doing so would mean
    the first migration had fixed the wrong one.
    """

    def test_the_project_uses_its_own_user_model(self) -> None:
        from django.conf import settings

        assert settings.AUTH_USER_MODEL == "accounts.User"
