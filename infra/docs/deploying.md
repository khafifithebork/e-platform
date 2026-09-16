# Deploying

What happens on a merge to `master`, and what has to exist first.

**`provisioning.md` is the companion to this file** — what has to be created, in what order, and what it costs. Read that first if nothing exists yet.

**The pipeline is dormant.** Every deploy job is gated on the repository
variable `DEPLOY_ENABLED`, which is unset. Nothing exists to deploy to yet, and
a pipeline that fails on every merge until somebody provisions is a pipeline
people learn to ignore — an ignored red build is worse than no build.

---

## The sequence

```
push to master
      │
      ├── backend tests ─┐
      ├── frontend tests ─┴──► deploy-staging ──► deploy-production
      │                          (no gate)         (approval required)
```

`needs:` is what makes "only after the tests pass" structural rather than a
convention, and it is asserted in `tests/unit/test_deploy_pipeline.py`.

Within each environment, the order is not arbitrary:

1. **`check_database`** — read-only. `catalog.0005_search_vector` is
   `atomic = False`, so a missing extension found by `migrate` can leave an
   `INVALID` index needing manual cleanup. Found here it costs a failed step.
2. **`predeploy`** — migrations, over the **direct** connection, holding a lock
   it verifies is actually held.
3. **The API**, then a poll on `/healthz`.
4. **The Worker**, built against the API that is now running.

**Step 4 must follow step 3**, and that is forced rather than chosen: the public
catalogue is statically generated from the API (ADR-024), so the Worker build
reads whatever the API is serving. Reversed, a release bakes the previous
catalogue — against a schema the migrations have already changed — and every
page looks fine.

---

## Production is one approved action

`deploy-production` names a GitHub Environment. **The approval lives in that
environment's protection rules, not in YAML** — GitHub does this deliberately,
so that a pull request cannot remove its own gate.

Configure it once, in repository settings: *Environments → production →
Required reviewers*. Until that is set, "approved" is a claim this repository
makes and cannot keep.

Staging deliberately has no gate. The thing being approved for production has
already run somewhere.

---

## What must be configured

### Repository variables

| Variable | Purpose |
|---|---|
| `DEPLOY_ENABLED` | `true` switches the pipeline on. Nothing deploys without it |
| `STAGING_API_ORIGIN` · `PRODUCTION_API_ORIGIN` | **Baked into the frontend at build time.** One build cannot serve two environments |
| `STAGING_WORKER_NAME` · `PRODUCTION_WORKER_NAME` | Cloudflare Worker per environment |
| `STAGING_WEB_URL` · `PRODUCTION_WEB_URL` | Shown on the deployment in GitHub's UI |

### Environment secrets

**There are two different places environment values live, and putting one in
the other is a silent no-op.**

- **GitHub environment secrets** — what *CI* needs: to run migrations from the
  runner, and to build and deploy the Worker.
- **Dokploy's application environment** — what the *running containers* need.
  `infra/hetzner/README.md` has that list.

`METRICS_TOKEN` was in the table below until 2026-09-16 and **nothing in CI has
ever read it**. It is a container variable; setting it as a GitHub secret does
nothing at all, and the endpoint stays a 404 while somebody wonders why.

Set these per environment, so staging cannot reach production's database. Every
one is required unless marked otherwise — the deploy action declares them so,
and `test_deploy_pipeline.py` asserts the workflow passes them.

| Secret | Note |
|---|---|
| `DATABASE_URL_DIRECT` | **Direct, not pooled.** See below |
| `DJANGO_SECRET_KEY` | Different per environment |
| `REDIS_URL` | Celery broker |
| `REDIS_CACHE_URL` | Cache and throttle counters. **A different database number** from the broker |
| `MEDIA_STORAGE_ENDPOINT` | R2 S3 API endpoint |
| `MEDIA_STORAGE_BUCKET` | R2 bucket name |
| `MEDIA_STORAGE_ACCESS_KEY` | R2 access key id |
| `MEDIA_STORAGE_SECRET_KEY` | R2 secret access key |
| `DOKPLOY_URL` · `DOKPLOY_API_KEY` | |
| `DOKPLOY_APPLICATION_IDS` | Comma-separated: the `api` and the `worker` are separate Dokploy applications running the same image |
| `CLOUDFLARE_API_TOKEN` · `CLOUDFLARE_ACCOUNT_ID` | |
| `SENTRY_DSN_BROWSER` | **Optional.** Baked into the bundle at build time, so it can only be set here. Empty means the browser SDK never initialises. Give each environment its own Sentry project (ADR-027 §2) |

The four `MEDIA_STORAGE_` names are spelled out rather than abbreviated to
`MEDIA_STORAGE_*`, which is how three of four get set.

**Why the direct connection.** `predeploy` takes a session-level advisory lock
so two rollouts cannot migrate at once. Neon's documentation lists exactly that
among the features its transaction-mode pooler does not support — over the
pooled host the lock is granted and held by nothing, and the second deploy is
told to proceed. `predeploy` refuses rather than trusting the input, so the
symptom is a failed deploy rather than a silent one. `infra/neon/README.md` has
the detail.

The application containers keep using the **pooled** string. Only migrations
need the direct one.

---

## What has never been run

**All of it.** This pipeline has never executed, because there is nothing to
deploy to. Its structure is asserted by tests — ordering, gating, which
connection string, which origin — and structure is not behaviour.

Two things in particular are unverified:

- **Dokploy's deploy API.** `POST /api/application.deploy` with an `x-api-key`
  header, taken from Dokploy's own documentation. The request shape has not
  been exercised against a real instance.
- **`opennextjs-cloudflare deploy`.** The build is proven (M13 T7); the deploy
  is not, and neither is the `/api/*` rewrite through a running Worker — which
  ADR-025 names as the one unknown the spike did not close.

**M13 T10 is where this stops being theory.** Its rehearsal — deploy something
deliberately broken, notice it, roll it back by the runbook without reading
ahead — is the first time any of this runs against a real environment.
`docs/runbooks/rollback.md` §6 says it plainly: *"a runbook that has never been
executed is a guess about your own systems."* So is a pipeline.
