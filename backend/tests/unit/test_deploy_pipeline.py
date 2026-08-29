"""The deploy pipeline's structure. M13 T9.

**None of this can be tested by running it**, because running it deploys. What
can be asserted is the shape, and the shape carries three properties whose
absence would be found in production rather than in CI:

- Deploy happens **only after the tests pass**, and only on `master`.
- Production is reached **through staging**, and behind an approval.
- The API is deployed **before** the frontend, because the public catalogue is
  statically generated from it (ADR-024).

The last one is the least obvious and the most expensive. Reversed, a release
would bake the previous catalogue against a schema the new migrations had
already changed, and every page would look fine.

`docs/runbooks/rollback.md` exists because this pipeline can be wrong. These
tests exist because some ways of being wrong are silent.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_ACTION = REPO_ROOT / ".github" / "actions" / "deploy" / "action.yml"


def _workflow() -> dict:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _action() -> dict:
    return yaml.safe_load(DEPLOY_ACTION.read_text(encoding="utf-8"))


def _step_names() -> list[str]:
    return [step.get("name") or step.get("uses", "") for step in _action()["runs"]["steps"]]


class TestDeployHappensOnlyAfterTheTestsPass:
    def test_staging_needs_both_test_jobs(self) -> None:
        """`needs` rather than convention. A separate workflow triggered by
        `workflow_run` would express the same intent and would run against the
        default branch's copy of itself, which is a subtlety nobody wants to
        reason about while a deploy is going wrong."""
        needs = _workflow()["jobs"]["deploy-staging"]["needs"]

        assert set(needs) == {"backend", "frontend"}

    def test_production_comes_after_staging(self) -> None:
        """The thing being approved has already run somewhere."""
        assert _workflow()["jobs"]["deploy-production"]["needs"] == ["deploy-staging"]

    def test_neither_deploys_from_a_branch(self) -> None:
        """CI runs on every branch — `branches: ["**"]`. Without the ref guard,
        pushing a spike would deploy it."""
        for job in ("deploy-staging", "deploy-production"):
            condition = _workflow()["jobs"][job]["if"]

            assert "refs/heads/master" in condition, job

    def test_neither_deploys_from_a_pull_request(self) -> None:
        """A pull request from a fork must not be able to reach the deploy
        secrets, and `github.ref` alone does not say enough."""
        for job in ("deploy-staging", "deploy-production"):
            condition = _workflow()["jobs"][job]["if"]

            assert "github.event_name == 'push'" in condition, job

    def test_both_are_dormant_until_switched_on(self) -> None:
        """Nothing exists to deploy to yet. A pipeline that fails on every
        merge until somebody provisions is a pipeline people learn to ignore,
        and an ignored red build is worse than no build."""
        for job in ("deploy-staging", "deploy-production"):
            condition = _workflow()["jobs"][job]["if"]

            assert "vars.DEPLOY_ENABLED" in condition, job


class TestProductionIsOneApprovedAction:
    def test_it_names_a_github_environment(self) -> None:
        """The approval lives in the environment's protection rules, which
        GitHub deliberately does not express in YAML — so that a pull request
        cannot remove its own gate. What this file can assert is that the job
        is attached to the environment where such a rule can exist."""
        assert _workflow()["jobs"]["deploy-production"]["environment"]["name"] == "production"

    def test_staging_is_a_different_environment(self) -> None:
        """Sharing one environment would mean sharing its protection rule, and
        an approval prompt before every staging deploy is an approval nobody
        reads."""
        assert _workflow()["jobs"]["deploy-staging"]["environment"]["name"] == "staging"


class TestTheOrderTheStepsRunIn:
    def test_the_database_is_asked_before_it_is_migrated(self) -> None:
        """`check_database` is read-only and cheap to fail.
        `0005_search_vector` is `atomic = False`, so a missing extension found
        by `migrate` can leave an INVALID index needing manual cleanup."""
        script = _action()["runs"]["steps"][2]["run"]

        assert script.index("check_database") < script.index("predeploy")

    def test_the_api_is_deployed_before_the_frontend(self) -> None:
        """**Forced by static generation.** The public catalogue is built from
        the API (ADR-024), so the Worker build reads whatever the API is
        serving. Reversed, a release bakes the previous catalogue — against a
        schema the migrations have already changed — and every page looks
        fine."""
        names = _step_names()

        assert names.index("Redeploy the API and worker") < names.index("Build the Worker")

    def test_it_waits_for_the_api_before_building_against_it(self) -> None:
        """A Worker built against a container still starting would bake an
        empty catalogue. `CatalogueUnavailable` catches that, but as a failed
        build rather than as the wait it actually needed."""
        names = _step_names()

        assert (
            names.index("Redeploy the API and worker")
            < names.index("Wait for the API to answer")
            < names.index("Build the Worker")
        )

    def test_migrations_run_before_anything_is_deployed(self) -> None:
        """Old code against a new schema is survivable and is what
        `rollback.md` §3.1 plans for. New code against an old schema is not."""
        names = _step_names()

        assert names.index("Preflight, then migrate") < names.index("Redeploy the API and worker")


class TestTheThingsThatWouldBreakSilently:
    def test_the_worker_is_built_with_this_environment_s_api_origin(self) -> None:
        """**The origin is baked in at build time** — Next serializes rewrites
        into the build output, so one build cannot serve two environments
        (M15 spec §4.3). A Worker built without it proxies to a localhost that
        does not exist on Cloudflare's edge."""
        build = next(s for s in _action()["runs"]["steps"] if s.get("name") == "Build the Worker")

        assert "API_ORIGIN" in build.get("env", {})

    def test_the_browser_sentry_dsn_is_supplied_at_build_time(self) -> None:
        """**It can only be supplied here.** `NEXT_PUBLIC_` values are inlined
        into the client bundle during the build, so setting the DSN on a
        container does nothing — the same property `api-origin` has, and the
        same reason one build cannot serve two environments.

        The failure this catches is quiet: no DSN at build time produces a
        Worker whose browser SDK never initialises, and a Sentry project that
        simply stays empty looks identical to an application with no errors.
        M14 T5, ADR-027."""
        build = next(s for s in _action()["runs"]["steps"] if s.get("name") == "Build the Worker")

        assert "NEXT_PUBLIC_SENTRY_DSN" in build.get("env", {})

    def test_each_environment_reports_under_its_own_name(self) -> None:
        """Staging errors landing in production's issue list is how an alert
        that matters gets triaged as noise."""
        jobs = _workflow()["jobs"]
        named = {
            job: next(
                step["with"]
                for step in jobs[job]["steps"]
                if step.get("uses") == "./.github/actions/deploy"
            )["sentry-environment"]
            for job in ("deploy-staging", "deploy-production")
        }

        assert named["deploy-staging"] != named["deploy-production"]

    def test_migrations_use_the_direct_connection_not_the_pooled_one(self) -> None:
        """`predeploy` takes a session-level advisory lock, which Neon's
        transaction-mode pooler does not support — it would be granted and held
        by nothing, and two rollouts would both proceed. `predeploy` refuses
        rather than trusting this, and pointing it at the pooled host turns a
        deploy into a failed deploy."""
        migrate = next(
            s for s in _action()["runs"]["steps"] if s.get("name") == "Preflight, then migrate"
        )

        assert "database-url-direct" in migrate["env"]["DATABASE_URL"]

    def test_the_static_checks_run_against_the_artifact_being_deployed(self) -> None:
        """Not against a local build of it. `verify:static` is the only thing
        that catches a route going dynamic for a reason nobody wrote down."""
        build = next(s for s in _action()["runs"]["steps"] if s.get("name") == "Build the Worker")

        assert "verify:static" in build["run"]
        assert "verify:a11y" in build["run"]

    def test_the_action_uses_no_yaml_anchors(self) -> None:
        """GitHub added anchor support in September 2025 and still does not
        support merge keys. Whether a composite action's parser honours either
        is not something a deploy pipeline should discover at 3am, so this file
        uses neither."""
        raw = DEPLOY_ACTION.read_text(encoding="utf-8")

        assert "&django-env" not in raw
        assert "*django-env" not in raw


class TestOneActionServesBothEnvironments:
    def test_staging_and_production_run_the_same_steps(self) -> None:
        """Two copies would drift, and the copy that drifts is the one nobody
        has open when they change the other — which for a deploy pipeline means
        the environment you rehearse on stops resembling the one you deploy to.
        M13 T10's rehearsal depends on exactly that not happening."""
        jobs = _workflow()["jobs"]
        used = {
            job: [step.get("uses") for step in jobs[job]["steps"] if step.get("uses")]
            for job in ("deploy-staging", "deploy-production")
        }

        assert used["deploy-staging"] == used["deploy-production"]
        assert "./.github/actions/deploy" in used["deploy-staging"]

    def test_they_differ_only_in_their_inputs(self) -> None:
        """The twin. Identical `uses` proves they call the same action; this
        proves they are not accidentally passing identical inputs, which would
        deploy staging's build to production."""
        jobs = _workflow()["jobs"]
        inputs = {
            job: next(
                step["with"]
                for step in jobs[job]["steps"]
                if step.get("uses") == "./.github/actions/deploy"
            )
            for job in ("deploy-staging", "deploy-production")
        }

        assert inputs["deploy-staging"]["api-origin"] != inputs["deploy-production"]["api-origin"]
        assert inputs["deploy-staging"]["worker-name"] != inputs["deploy-production"]["worker-name"]
