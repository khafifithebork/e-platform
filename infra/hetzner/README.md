# The Hetzner box

The Django half of B-lite (ADR-025). Next.js is not here — it runs on
Cloudflare Workers, and `infra/cloudflare/` holds that side.

**Nothing in this directory provisions anything.** It is the record of what the
box must be configured to do, so that rebuilding it is a repeatable act rather
than an archaeology exercise, and so a reviewer can read the settings without
logging in.

---

## What runs here

| Container | Why |
|---|---|
| `api` | Django under ASGI (invariant 12), serving `/api/*`, `/healthz`, `/admin/*` |
| `worker` | Celery **with Beat**, at exactly one replica |
| `redis` | Broker, cache and throttle counters |

**Not here, and each absence is a decision:**

- **Postgres** — Neon holds it. `deployment-strategy.md`'s Architecture A
  diagram puts it in a container; ADR-002 chose managed instead, so
  point-in-time recovery and version upgrades are somebody else's job rather
  than the thing that wakes you up.
- **Object storage** — Cloudflare R2. MinIO exists only so development needs no
  bucket.
- **Next.js** — Cloudflare Workers. That is what B-lite *is*.

---

## The deploy sequence

Dokploy pulls the image and restarts containers. **Migrations are not part of
that**, and must run first:

```bash
python manage.py predeploy
```

Built at M13 T3 for exactly this. It waits for the database with a bounded
retry, takes a Postgres advisory lock so two concurrent deploys cannot migrate
at once, applies migrations, and **does nothing else** — a structural test
forbids backfills, which belong in their own chunked commands (invariant 14).

Configure it as Dokploy's pre-deploy command. Running it inside the app
container's entrypoint instead would run it once per replica, which is what the
advisory lock exists to survive but not what it exists to encourage.

`docs/runbooks/rollback.md` §1 opens with the question this makes answerable:
*has a migration been applied?*

---

## What must be set, and where

Every value comes from the environment; **none of it belongs in this
repository**. `backend/.env.example` documents the names and nothing else
(CLAUDE.md §6).

Dokploy holds them. **How it supplies them to the containers is not verified** —
it may write a `.env` beside the compose file or inject them directly, and the
two differ in what happens when one is missing. Confirm against Dokploy's own
documentation before the first deploy rather than trusting this file; §6
forbids inventing a provider capability and this is one.

The ones without which nothing starts:

`DJANGO_SECRET_KEY` · `DJANGO_ALLOWED_HOSTS` · `DATABASE_URL` (Neon, **pooled**) ·
`REDIS_URL` · `REDIS_CACHE_URL` · `MEDIA_STORAGE_*` (R2) · `OPERATIONS_ALERT_EMAIL`

**`predeploy` needs a different one.** It takes a session-level advisory lock,
which Neon's documentation lists among the features its transaction-mode pooler
does not support — over the pooled string the lock is granted and held by
nothing, and two concurrent deploys both proceed. Give the pre-deploy step the
**direct** connection string, the host without `-pooler`. `infra/neon/README.md`
has the detail, and `predeploy` now refuses rather than trusting the caller.

Two that are easy to miss because nothing fails loudly without them:

- **`OPERATIONS_ALERT_EMAIL`** — empty means the nightly entitlement
  reconciliation finds drift and tells nobody. It logs
  `entitlement_drift_unreported_no_recipient` and carries on (M14 T4).
- **`IMAGE_REGISTRY` / `IMAGE_TAG`** — the compose file reads both. CI tags
  images with the commit SHA; `docs/runbooks/rollback.md` §2 depends on being
  able to name a previous one.

---

## What is still the owner's to do

Configuration lives here. **Provisioning happens in a browser, by a person**,
and none of it is mine:

1. Create the Cloudflare, Hetzner and Neon accounts, and enter payment details.
2. Create the CX33 in a Frankfurt-adjacent region (architecture.md §3: EU, with
   learners in EU and MENA).
3. Install Dokploy on it and point it at this compose file.
4. Create the Neon project and a **branch for staging** — M13 T8, and the place
   `pg_trgm` has to be verified, because M12 handed that over as unverified
   anywhere but development.
5. Set the environment above in Dokploy.
6. Point DNS at the box for the API hostname, through Cloudflare.

---

## Before the first real deploy

**The `/api/*` rewrite has never been proven through a running Worker.**
ADR-025 names this as the one unknown the spike did not close. The check is not
that a request arrives but that **the session cookie survives the round trip in
both directions** — invariant 9 and ADR-001 §2.1 both rest on it. Perhaps
thirty minutes with `wrangler dev` against a live Django.

**And the rollback runbook has never been rehearsed.** `docs/runbooks/rollback.md`
§6 says so plainly: *"a runbook that has never been executed is a guess about
your own systems."* M13 T10 is that rehearsal, and it needs this box to exist.
