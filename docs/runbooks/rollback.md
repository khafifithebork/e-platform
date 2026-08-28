# Runbook — rolling back a deploy

**Status: written, NOT rehearsed.** M13's objective asks for a rollback
procedure "documented **and** rehearsed". Rehearsing needs a running
environment, and CLAUDE.md §11 #3 (hosting target) has not chosen one. Until somebody has
actually done this against a real deployment, treat every step below as a
plan rather than a tested procedure — the difference has bitten this project
before, and ADR-023 §1 is about exactly that.

**Read §1 before touching anything.** It is thirty seconds and it decides
which of two very different procedures you are in.

---

## 1. First question: has a migration been applied?

Rolling back **code** is easy and safe. Rolling back **schema** is often
impossible. Everything else in this runbook follows from which one you are in.

```
Did this release apply a migration?
    │
    ├── No  → §2. Redeploy the previous image. ~2 minutes. Safe.
    │
    └── Yes → §3. Do NOT reflexively redeploy the old image.
              The old code may not run against the new schema.
```

**How to find out, without guessing:**

```bash
# In a container running the NEW image, against the live database:
python manage.py predeploy --check
```

Exit 0 means the database matches this release, so this release either applied
migrations or needed none. That does not tell you *which*. For that:

```bash
python manage.py showmigrations --plan | tail -20
```

Compare against the previous release's tag. `git diff <previous-sha> <current-sha> -- backend/apps/*/migrations/` is the authoritative answer and takes ten seconds.

---

## 2. Code-only rollback — no migration in this release

The safe path.

> **Blocker, today: there is no registry.** M13 T4 builds and tags the release
> image in CI and deliberately does **not** push it — pushing needs a registry,
> a registry needs an account, and §11 #3 has not chosen a platform. So the
> images this section tells you to redeploy **do not exist anywhere outside the
> CI runner that built them**. Until T7–T10 land, a "rollback" means rebuilding
> the previous commit from source, which is slower and needs CI to be healthy.
> This is written down rather than glossed because a runbook whose first step
> is impossible is worse than none.

1. **Identify the last good image.** CI tags every image with the commit SHA
   (`e-platform-backend:<sha>`), so the previous release is the SHA of the
   commit before the merge.
2. **Point the platform at that tag** and redeploy. *(Platform-specific — fill
   in when §11 #3 is answered. On Render this is "Rollback to this deploy"; on
   Dokploy it is redeploying the previous tag.)*
3. **Verify with the same check CI uses**, rather than by looking at the page:

   ```bash
   scripts/smoke_release.sh e-platform-backend:<previous-sha>
   ```

4. **Confirm the running version.** A rollback that silently did nothing looks
   identical to one that worked.

**Expected duration: 2–5 minutes**, dominated by the platform's pull and
health-check cycle.

---

## 3. A migration was applied — the hard case

**Do not start by redeploying the old image.** The old code will run against
the new schema, and whether that works depends entirely on what the migration
did:

| The migration… | Old code against new schema | What to do |
|---|---|---|
| **Added** a nullable column, a table, or an index | Works. The old code ignores it. | §3.1 — roll back code only, leave the schema |
| **Added** a non-nullable column with no default | Old inserts fail | §3.2 — forward-fix |
| **Removed or renamed** a column the old code reads | Old code raises on every query touching it | §3.2 — forward-fix |
| **Changed** a constraint the old code violates | Writes fail, reads work | §3.2 — forward-fix |

### 3.1 Roll back code, leave the schema

This is the right answer far more often than reversing a migration, and it is
the reason additive migrations are worth insisting on. Follow §2 and stop.
The extra column sits unused until the fix rolls forward.

### 3.2 Forward-fix, do not reverse

**Reversing a migration in production is a last resort, not a rollback
strategy.** `migrate <app> <previous>` will happily drop a column, and the
data in it is gone.

Prefer, in order:

1. **Fix forward.** A new commit that repairs the defect, through the normal
   pipeline. Slower to write, but it is the only option that never destroys
   data.
2. **Disable the feature** if it is gated, rather than removing its schema.
3. **Reverse the migration** only if it is provably additive-and-empty — a
   column nothing has written to yet — and only with a database backup taken
   *first*.

### This repository's known-awkward migration

**`catalog.0005_search_vector` reverses, but not atomically.** It is
`atomic = False`, which `CREATE INDEX CONCURRENTLY` requires, and a non-atomic
migration has no transaction to undo.

**Observed, not assumed:** this migration was rolled back and re-applied
against a live Postgres during M13 T3, and both directions worked. So the
reversal is not the hazard. These two are:

- **A part-way failure leaves no clean state.** The index can be left `INVALID`
  and must be dropped by hand before a retry. Nothing rolls that back for you.
- **Reversing drops `search_vector` and the `pg_trgm` extension.** The column
  is derived, so it is rebuildable with `manage.py backfill_search_vectors` —
  but that is a separate chunked command over every course, not instant, and
  search returns nothing until it finishes.

It is the only migration in the repository with that property today. Check for
others before assuming:

```bash
grep -rl "atomic = False\|RunPython\|RunSQL" backend/apps/*/migrations/
```

---

## 4. What a rollback does not fix

Stated plainly, because the instinct under pressure is to roll back and assume
the problem is gone.

- **Work already queued.** Celery tasks enqueued by the bad release are still
  in Redis and will run against the rolled-back code. Redis is disposable by
  design (ADR-002 §4), so purging the queue is a legitimate option — at the
  cost of losing whatever legitimate work is in it.
- **Email already sent.** M11's delivery is at-least-once and stores nothing
  (ADR-021 §5). Anything sent is gone.
- **Rows already written.** A rollback moves code, not data. A bad release that
  wrote wrong rows needs a data fix, which is its own piece of work.
- **Audit rows.** `AuditLog` is append-only and will retain what the bad
  release recorded. That is correct — the trail is of what happened, not of
  what we wish had happened.

---

## 5. After any rollback

1. **Write down what happened before the adrenaline fades.** Which release,
   what symptom, which path in §1 you took, how long it took.
2. **Decide whether the pipeline should have caught it.** M13 T4 and T5 exist
   because "surely someone would notice" is not a control. If the smoke check
   could have caught this, extend it.
3. **If a migration was involved, say so in the post-mortem.** The migration
   discipline in invariant 14 — additive changes, backfills as separate
   commands — is what keeps §3.1 available instead of §3.2.

---

## 6. Rehearsal — outstanding

**Nobody has performed this**, and it is not currently possible: there is no
environment to roll back and no registry to roll back *to* (see §2). The
objective says "documented and rehearsed", and only the first half is done.

The rehearsal, when there is an environment:

1. Deploy a release with a deliberate, obvious defect — a wrong string on the
   health endpoint is enough.
2. Notice it the way you would in production.
3. Roll back by §2 without reading ahead.
4. Time it, and record what the runbook got wrong.

**A runbook that has never been executed is a guess about your own systems.**
Writing it first is what makes the rehearsal a test rather than an
improvisation — but the test still has to happen.
