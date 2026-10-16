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

    **The audits became their own jobs on 2026-10-03**, and this class moved
    with them. The reason is in the workflow: as steps inside `backend` and
    `frontend` they ran early, and GitHub stops a job at its first failing step,
    so a `braces` advisory with no patched version at any release reported type
    check, lint, 649 tests, the build and all four `verify:*` scripts as
    *skipped*. CI could not say whether any change on any branch was correct.

    Everything this class asserted before, it still asserts. One assertion was
    added, because splitting opened a hole that did not exist when these were
    steps: a whole job can be marked `continue-on-error`, which neuters the gate
    without touching the command or the step.
    """

    #: The jobs that exist to run an audit and nothing else.
    AUDIT_JOBS = ("audit-backend", "audit-frontend")

    #: The jobs that must *not* contain one, because a failing audit inside them
    #: skips everything behind it.
    TEST_JOBS = ("backend", "frontend")

    @staticmethod
    def _run_steps(job: str) -> list[str]:
        return [
            step["run"]
            for step in _workflow()["jobs"][job]["steps"]
            if isinstance(step, dict) and "run" in step
        ]

    @classmethod
    def _run_commands(cls, job: str) -> list[str]:
        """`run:` scripts with their shell comments stripped.

        **Needed, not tidiness.** `backend`'s install step carries a comment
        explaining why the install is editable — and that comment contains the
        literal string `pip-audit`. A check for "no audit command in the test
        jobs" that read the raw script would fail against entirely correct
        configuration, which is the comments-versus-code trap this repository
        has now hit seven times. Caught here before it was written, for once,
        because the job graph was printed before the test was.
        """
        stripped = []
        for script in cls._run_steps(job):
            lines = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
            stripped.append("\n".join(lines))
        return stripped

    def test_the_backend_audits_its_dependencies(self) -> None:
        assert any(
            "pip_audit" in step or "pip-audit" in step
            for step in self._run_commands("audit-backend")
        )

    def test_the_frontend_audits_its_dependencies(self) -> None:
        commands = self._run_commands("audit-frontend")
        assert any("node scripts/assert-dependency-audit.mjs" in step for step in commands)
        assert any(
            "node --test scripts/assert-dependency-audit.test.mjs" in step for step in commands
        )

    def test_the_frontend_audit_is_not_left_on_the_default_level(self) -> None:
        """`npm audit` with no level fails on `low`. That is the version that
        gets disabled."""
        script = (REPO_ROOT / "frontend/scripts/assert-dependency-audit.mjs").read_text(
            encoding="utf-8"
        )
        assert '"audit", "--json", "--audit-level=high"' in script

    def test_the_frontend_audit_is_not_softened(self) -> None:
        audits = [
            step
            for step in self._run_commands("audit-frontend")
            if "assert-dependency-audit" in step
        ]
        assert audits
        assert all("|| true" not in step and "continue-on-error" not in step for step in audits)

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
            for step in self._run_commands("audit-backend")
            if "pip_audit" in step or "pip-audit" in step
        ]

        assert audits
        assert all("|| true" not in step and "continue-on-error" not in step for step in audits)

    def test_no_audit_runs_inside_a_job_that_does_other_work(self) -> None:
        """The reason for the split, asserted so it cannot quietly come back.

        An audit step added to `backend` or `frontend` would restore exactly the
        failure of 2026-10-03: one unfixable advisory, and every check behind it
        reported as skipped rather than run. The tempting version of that
        regression is somebody moving the step back to keep a job count down.
        """
        for job in self.TEST_JOBS:
            for command in self._run_commands(job):
                assert "pip_audit" not in command, job
                assert "pip-audit" not in command, job
                assert "npm audit" not in command, job
                assert "node scripts/assert-dependency-audit.mjs" not in command, job

    def test_no_audit_step_is_marked_continue_on_error(self) -> None:
        """The other way to neuter a gate: leave the command alone and tell the
        runner to ignore its exit code."""
        for job in self.AUDIT_JOBS:
            for step in _workflow()["jobs"][job]["steps"]:
                if isinstance(step, dict) and "audit" in str(step.get("name", "")).lower():
                    assert not step.get("continue-on-error"), (job, step.get("name"))

    def test_no_audit_job_is_marked_continue_on_error(self) -> None:
        """**New with the split, because the split created it.**

        When the audits were steps, `continue-on-error` on the job would have
        disabled the tests too — nobody would do it by accident. Now that each
        audit is a job of its own, one line at job level turns a red gate green
        and touches nothing else. That is the cheapest possible way to undo this
        work, so it is asserted.
        """
        for job in self.AUDIT_JOBS:
            assert not _workflow()["jobs"][job].get("continue-on-error"), job


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


class TestCiAndComposeAgreeOnTheObjectStore:
    """The suite must run against the same object store in both places.

    **This is the fifth instance of the pattern this file exists for**, arriving
    from a direction none of the checks above cover: not a missing variable, but
    the same fact written in two files that can drift apart.

    It surfaced on 2026-09-14 when Docker Hub began refusing anonymous pulls of
    `minio/minio` and took CI down. Local machines had the image cached and kept
    working, so the build looked broken by whichever commit happened to land
    that morning. Eleven days later quay.io refused it too — every tag, `latest`
    and a 2024 release alike — and the store was replaced with LocalStack.

    **The vendor has now changed twice, so this no longer names one.** The
    image is read from compose and compared, whatever it is; `_ci_image`
    matches the argument that looks like an image reference rather than a
    particular repository. Naming the vendor here would mean this guard needs
    editing every time the thing it guards is replaced — and a guard that must
    be edited to keep passing is one somebody edits without thinking.
    """

    @staticmethod
    def _compose_image() -> str:
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        return compose["services"]["storage"]["image"]

    @classmethod
    def _storage_step(cls) -> str:
        steps = _workflow()["jobs"]["backend"]["steps"]
        return next(s["run"] for s in steps if "docker run" in str(s.get("run", "")))

    @classmethod
    def _ci_image(cls) -> str:
        """The image argument of the `docker run` line.

        Read from that line alone, not the whole script: the first version
        searched the step and matched the health-probe URL, which also contains
        a slash and a colon. An image reference never starts with a dash, never
        contains `//`, and — unlike a `4566:4566` port mapping — does not have
        digits on both sides of its colon.
        """
        line = next(row for row in cls._storage_step().splitlines() if "docker run" in row)
        candidates = [
            token
            for token in line.split()
            if ":" in token
            and not token.startswith("-")
            and "//" not in token
            and not token.rsplit(":", 1)[0].isdigit()
        ]
        assert candidates, f"no image reference found in: {line}"
        return candidates[-1]

    def test_they_pull_the_same_image(self) -> None:
        assert self._ci_image() == self._compose_image()

    def test_the_tag_is_pinned_rather_than_floating(self) -> None:
        """`latest` would mean the version under test changes without a commit,
        and the failure would arrive on an unrelated pull request.

        It is also a concrete refusal now rather than a precaution:
        `localstack/localstack:latest` is the licence-gated Pro image, which
        boots and then exits 55 demanding an auth token."""
        image = self._compose_image()

        assert ":" in image, image
        assert not image.endswith(":latest"), image

    def test_the_guard_would_notice_a_difference(self) -> None:
        """The twin. Both halves read real files, so a matcher that found
        nothing would make the first test compare two empty strings and pass."""
        assert ":" in self._compose_image()
        assert ":" in self._ci_image()
        assert "/" in self._ci_image()


class TestPresignedSignaturesAreActuallyVerified:
    """**The control that is one deleted line from being meaningless.**

    `test_object_storage.py` asserts twice that the store answers 403 when a
    presigned URL is tampered with — once for a substituted content type, once
    for a retargeted object key. Both are abuse case 2, and they are the reason
    ADR-012 §1 made this adapter real rather than fake.

    LocalStack ships with presigned-signature validation **off**. Measured on
    2026-09-25: with `S3_SKIP_SIGNATURE_VALIDATION` at its default those two
    tests fail and the other fifteen pass. So the flag is what makes those
    assertions mean anything, and dropping it from either file would turn a
    security control green rather than red — which is the failure this whole
    file exists to catch, in its most expensive form.

    Adobe's `s3mock` was the first candidate and was rejected for exactly this:
    its own documentation says presigned URLs are "accepted but not validated
    (expiration, signature, HTTP verb not checked)".
    """

    FLAG = "S3_SKIP_SIGNATURE_VALIDATION"

    def test_ci_starts_the_store_with_validation_on(self) -> None:
        steps = _workflow()["jobs"]["backend"]["steps"]
        script = next(s["run"] for s in steps if "docker run" in str(s.get("run", "")))

        assert f"{self.FLAG}=0" in script

    def test_compose_starts_the_store_with_validation_on(self) -> None:
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        environment = compose["services"]["storage"]["environment"]

        assert str(environment[self.FLAG]) == "0"

    def test_the_two_assertions_it_protects_still_exist(self) -> None:
        """**Without this, the guard above guards nothing.** Deleting the two
        403 tests would leave the flag set, correct, and pointless — and every
        test in this file would still pass."""
        source = (
            REPO_ROOT / "backend" / "tests" / "integration" / "test_object_storage.py"
        ).read_text(encoding="utf-8")

        assert "def test_the_store_refuses_a_different_content_type" in source
        assert "def test_the_url_authorises_one_key_only" in source
        assert source.count("== 403") >= 2
