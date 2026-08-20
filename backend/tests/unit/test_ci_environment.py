"""CI must supply every environment variable production settings require.

This guards a failure that has now happened three times in different guises:
a required variable is added to ``base.py``, and one of the several places that
must also learn about it is missed. ``.env.example`` has a drift test.
``test.py`` seeds its own. ``docker-compose.yml`` sets them. The CI workflow
had nothing checking it, and duly went stale.

The failure mode is unpleasant out of proportion to the cause: the whole
``check --deploy`` step dies with a traceback that looks like a Django problem
rather than a missing line in a YAML file.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BASE_SETTINGS = REPO_ROOT / "backend" / "config" / "settings" / "base.py"

DEPLOY_STEP_NAME = "Deployment check"

# A read with no `default=` argument — the closing paren follows the name
# directly. Those are the variables whose absence stops the process at import.
_REQUIRED_READ = re.compile(r"\benv(?:\.\w+)?\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']\s*\)")

# Variables the step exports inside its shell script rather than declaring in
# `env:` — DJANGO_SECRET_KEY is generated per run.
_SHELL_EXPORT = re.compile(r"\bexport\s+([A-Z][A-Z0-9_]*)=")


def _required_by_settings() -> set[str]:
    return set(_REQUIRED_READ.findall(BASE_SETTINGS.read_text(encoding="utf-8")))


def _workflow() -> dict:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _deployment_check_step() -> dict:
    workflow = _workflow()

    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == DEPLOY_STEP_NAME:
                return step

    raise AssertionError(f"no {DEPLOY_STEP_NAME!r} step in {CI_WORKFLOW.name}")


def _provided_by_ci() -> set[str]:
    step = _deployment_check_step()
    return set(step.get("env", {})) | set(_SHELL_EXPORT.findall(step.get("run", "")))


class TestCiSuppliesTheRequiredEnvironment:
    def test_settings_declare_at_least_one_required_variable(self) -> None:
        """Guards the guard: if the regex stops matching, every other
        assertion here passes vacuously."""
        assert _required_by_settings(), "no required variables detected — regex is wrong"

    def test_every_required_variable_is_provided(self) -> None:
        missing = _required_by_settings() - _provided_by_ci()

        assert not missing, (
            f"{sorted(missing)} required by base.py but not supplied to the "
            f"{DEPLOY_STEP_NAME!r} step in ci.yml. The step will die with "
            "ImproperlyConfigured."
        )

    def test_the_secret_key_is_generated_rather_than_stored(self) -> None:
        """CLAUDE.md section 6. A repository secret would imply the value
        matters and teach the habit of putting keys in repo settings."""
        step = _deployment_check_step()

        assert "DJANGO_SECRET_KEY" not in step.get("env", {})
        assert "DJANGO_SECRET_KEY" in _SHELL_EXPORT.findall(step.get("run", ""))


class TestTheBackendJobRunsInTheBackend:
    """Every `run` in the backend job must execute in `backend/`.

    This is a config assertion and it earns its place: removing the
    `defaults.run.working-directory` key does not fail one step loudly, it
    silently relocates all of them. It was removed by accident in a commit
    that only meant to change how MinIO starts, and the visible symptom was
    `pip install ".[dev]"` reporting "Neither 'setup.py' nor 'pyproject.toml'
    found" — a message that points at packaging rather than at the directory.

    Asserted here rather than trusted because CI failing is the *only* other
    way to find out, and by then the build is red for a reason unrelated to
    the change that caused it.
    """

    def _backend_job(self) -> dict:
        return _workflow()["jobs"]["backend"]

    def test_the_working_directory_is_declared(self) -> None:
        working_directory = (
            self._backend_job().get("defaults", {}).get("run", {}).get("working-directory")
        )

        assert working_directory == "backend", (
            "the backend job must run in backend/, where pyproject.toml, "
            "manage.py and the tests live"
        )

    def test_the_steps_do_not_each_set_their_own(self) -> None:
        """One declaration, not one per step. A per-step setting is a thing to
        forget on the next step added."""
        overrides = [
            step.get("name")
            for step in self._backend_job()["steps"]
            if step.get("working-directory")
        ]

        assert not overrides, f"{overrides} override the job default; put it in defaults instead"
