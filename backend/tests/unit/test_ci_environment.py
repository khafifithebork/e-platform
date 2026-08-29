"""CI must supply every environment variable production settings require.

This guards a failure that has now happened **four** times in different guises:
a required variable is added to ``base.py``, and one of the several places that
must also learn about it is missed. ``.env.example`` has a drift test.
``test.py`` seeds its own. ``docker-compose.yml`` sets them. The CI workflow
had nothing checking it, and duly went stale.

The failure mode is unpleasant out of proportion to the cause: the step dies
with a traceback that looks like a Django problem rather than a missing line in
a YAML file.

**The fourth time got past this file**, because it checked one step by name.
M13 T8 added a `Database preflight` step that runs ``manage.py`` and supplied
only the variables that command touches — and ``manage.py`` defaults to
``config.settings.local``, which reads every one of them at import. A missing
``REDIS_URL`` stopped a database check that never opens a Redis connection.

So the check is no longer per-step. **Every step that runs ``manage.py`` is
covered**, because every one of them pays the same import cost.
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
    for _name, step in _manage_py_steps():
        if step.get("name") == DEPLOY_STEP_NAME:
            return step

    raise AssertionError(f"no {DEPLOY_STEP_NAME!r} step in {CI_WORKFLOW.name}")


def _manage_py_steps() -> list[tuple[str, dict]]:
    """Every step that runs ``manage.py``, with the job it belongs to.

    Named steps only: an unnamed one cannot be reported usefully when it fails,
    and every step in this workflow has a name.
    """
    found = []
    for job_name, job in _workflow()["jobs"].items():
        for step in job.get("steps", []):
            if "manage.py" in str(step.get("run", "")) and step.get("name"):
                found.append((job_name, step))
    return found


def _provided_to(step: dict) -> set[str]:
    return set(step.get("env", {})) | set(_SHELL_EXPORT.findall(step.get("run", "")))


class TestCiSuppliesTheRequiredEnvironment:
    def test_settings_declare_at_least_one_required_variable(self) -> None:
        """Guards the guard: if the regex stops matching, every other
        assertion here passes vacuously."""
        assert _required_by_settings(), "no required variables detected — regex is wrong"

    def test_at_least_one_step_runs_manage_py(self) -> None:
        """Guards the guard, again. If the search stops finding steps, the
        assertion below passes over an empty list."""
        assert _manage_py_steps(), "no manage.py steps found — the search is wrong"

    def test_every_step_running_manage_py_has_what_settings_require(self) -> None:
        """Every one of them, not only the deployment check.

        `manage.py` defaults to `config.settings.local`, which reads every
        required variable at import — so a step that only touches the database
        still needs the Redis URLs. Checking one step by name is what let M13
        T8 ship a `Database preflight` that died on `DJANGO_SECRET_KEY`.
        """
        required = _required_by_settings()
        failures = []

        for job_name, step in _manage_py_steps():
            missing = required - _provided_to(step)
            if missing:
                failures.append(f"{job_name} / {step['name']}: missing {sorted(missing)}")

        assert not failures, (
            "steps run manage.py without the environment base.py requires, and "
            "will die with ImproperlyConfigured:\n  " + "\n  ".join(failures)
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


class TestBothTiersAreAudited:
    """architecture.md §8.4: `pip-audit` and `npm audit` in CI.

    A config assertion, and it earns its place the same way the
    working-directory one above does: **the audit was specified in §8.4 and
    simply never added.** CI ran two jobs for eleven milestones and neither
    audited anything, and nothing reported that, because a missing step is
    silent by construction.

    The severities are asserted too, not just the presence of a step. `npm
    audit` without `--audit-level` fails on `low`, which is the setting that
    gets a `|| true` appended during an unrelated deadline — and a disabled
    audit is the failure mode ADR-022 §3 is designed against.
    """

    @staticmethod
    def _run_steps(job: str) -> list[str]:
        return [
            step["run"]
            for step in _workflow()["jobs"][job]["steps"]
            if isinstance(step, dict) and "run" in step
        ]

    def test_the_backend_audits_its_dependencies(self) -> None:
        assert any(
            "pip_audit" in step or "pip-audit" in step for step in self._run_steps("backend")
        )

    def test_the_frontend_audits_its_dependencies(self) -> None:
        assert any("npm audit" in step for step in self._run_steps("frontend"))

    def test_the_frontend_audit_is_not_left_on_the_default_level(self) -> None:
        """`npm audit` with no level fails on `low`. That is the version that
        gets disabled."""
        audits = [step for step in self._run_steps("frontend") if "npm audit" in step]

        assert audits
        assert all("--audit-level=high" in step for step in audits)

    def test_the_backend_audit_is_not_softened(self) -> None:
        """pip-audit has no severity filter, so there is nothing to tune — the
        only ways to soften it are `--ignore-vuln`, which is per-advisory and
        reviewable, and `|| true`, which is not. This catches the second.

        `--ignore-vuln` is deliberately *not* forbidden here: triaging a
        specific advisory and writing down why is the behaviour we want. Making
        it a code change that shows up in review is the control.
        """
        audits = [
            step
            for step in self._run_steps("backend")
            if "pip_audit" in step or "pip-audit" in step
        ]

        assert audits
        assert all("|| true" not in step and "continue-on-error" not in step for step in audits)

    def test_neither_audit_step_is_marked_continue_on_error(self) -> None:
        """The other way to neuter a gate: leave the command alone and tell the
        runner to ignore its exit code."""
        for job in ("backend", "frontend"):
            for step in _workflow()["jobs"][job]["steps"]:
                if isinstance(step, dict) and "audit" in str(step.get("name", "")).lower():
                    assert not step.get("continue-on-error"), (job, step.get("name"))


class TestDeploymentChecksRunInCi:
    """`manage.py check --deploy` is in the definition of done and in CI.

    Asserted for the same reason the audit steps above are: M12 found two
    controls that architecture.md described and nobody had built, and the way
    that happens is that a missing step is silent. This one *is* present — the
    assertion exists so it stays that way.

    It runs against **production** settings deliberately. Against the test
    settings it would inspect a configuration that never serves a request, and
    report clean while production had `DEBUG` on.
    """

    @staticmethod
    def _backend_runs() -> list[str]:
        return [
            step["run"]
            for step in _workflow()["jobs"]["backend"]["steps"]
            if isinstance(step, dict) and "run" in step
        ]

    def test_the_deployment_check_runs(self) -> None:
        assert any("check --deploy" in step for step in self._backend_runs())

    def test_it_runs_against_production_settings(self) -> None:
        """Read from the step's `env:` block, not from its `run:` string — the
        first version of this test looked in the command and failed against a
        workflow that was entirely correct. Where a setting is declared is part
        of what a config assertion has to know."""
        deploy_steps = [
            step
            for step in _workflow()["jobs"]["backend"]["steps"]
            if isinstance(step, dict) and "check --deploy" in step.get("run", "")
        ]

        assert deploy_steps
        for step in deploy_steps:
            assert step.get("env", {}).get("DJANGO_SETTINGS_MODULE") == (
                "config.settings.production"
            ), step.get("name")

    def test_the_resolver_coverage_gate_still_runs(self) -> None:
        """M4's gate, and the one §8.1 target that fails the build. It has been
        believed for eight milestones; T8 re-provoked it by adding an uncovered
        branch to the resolver, which took coverage to 96.21% and failed."""
        runs = self._backend_runs()

        assert any("--cov-fail-under=100" in step for step in runs)
        assert any("apps.entitlements.resolver" in step for step in runs)


class TestTheReleaseImagesAreBuilt:
    """CI builds the images that would deploy, not only the source.

    Everything else in the backend job tests the source on a GitHub runner:
    a different Python, different OS packages, an editable install and the dev
    dependency set. None of it exercises `--target runtime`. A Dockerfile that
    stopped building would be invisible until a deploy, which is the worst
    moment to find out — and this repository has now found four controls that
    a document described and nobody built, so "surely someone would notice" is
    not a control.

    **Not pushed anywhere.** Pushing needs a registry, a registry needs an
    account, and CLAUDE.md §11 #4 has not chosen a platform. Building without
    pushing is the half that is already decided, and the assertion below says
    so — a `docker push` appearing here would mean a hosting decision was made
    in a workflow file rather than by the owner.
    """

    @staticmethod
    def _runs(job: str) -> list[str]:
        return [
            step["run"]
            for step in _workflow()["jobs"][job]["steps"]
            if isinstance(step, dict) and "run" in step
        ]

    def test_the_backend_runtime_image_is_built(self) -> None:
        builds = [step for step in self._runs("backend") if "docker build" in step]

        assert builds
        assert any("--target runtime" in step for step in builds)

    def test_the_frontend_runtime_image_is_built(self) -> None:
        builds = [step for step in self._runs("frontend") if "docker build" in step]

        assert builds
        assert any("--target runtime" in step for step in builds)

    def test_the_dev_target_is_not_what_ships(self) -> None:
        """`--target dev` carries the reloader and the dev dependency set. A
        build that quietly used it would pass this file's other assertions."""
        for job in ("backend", "frontend"):
            for step in self._runs(job):
                if "docker build" in step:
                    assert "--target dev" not in step, job

    def test_nothing_is_pushed(self) -> None:
        for job in ("backend", "frontend"):
            for step in self._runs(job):
                assert "docker push" not in step, job
                assert "--push" not in step, job


class TestTheReleaseImageIsSmoked:
    """Building an image proves it builds. It does not prove it runs.

    M12 T7 is the case: adding `django-csp` to pyproject left every test green
    and every check clean, and the container then died with `No module named
    'csp'` because the image predated the dependency. `check --deploy` in this
    workflow cannot catch that — it runs on the runner, against a virtualenv
    with the dev dependency set installed.
    """

    @staticmethod
    def _runs(job: str) -> list[str]:
        return [
            step["run"]
            for step in _workflow()["jobs"][job]["steps"]
            if isinstance(step, dict) and "run" in step
        ]

    def test_the_smoke_check_runs(self) -> None:
        assert any("smoke_release.sh" in step for step in self._runs("backend"))

    def test_it_runs_after_the_image_is_built(self) -> None:
        """Order matters and is easy to lose in a reshuffle: smoking an image
        that does not exist yet fails for a reason that looks like the image
        being broken."""
        runs = self._runs("backend")
        build = next(i for i, step in enumerate(runs) if "docker build" in step)
        smoke = next(i for i, step in enumerate(runs) if "smoke_release.sh" in step)

        assert build < smoke

    def test_the_script_exists_and_is_executable_as_written(self) -> None:
        """The workflow calls it with `bash`, so the file has to be there and
        has to be a bash script. A renamed script fails at deploy-check time,
        which is late."""
        from pathlib import Path

        script = Path(__file__).resolve().parents[3] / "scripts" / "smoke_release.sh"

        assert script.exists()
        assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
