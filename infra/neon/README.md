# Neon

Postgres for B-lite (ADR-025). Not on the Hetzner box — `infra/hetzner/`
explains why the Architecture A diagram's containerised Postgres was not taken.

**Nothing here provisions anything.** Creating the project and its branches is
done in a browser, by a person.

---

## Two connection strings, and using the wrong one breaks a control

Neon offers a **pooled** endpoint and a **direct** one. They are not
interchangeable, and the difference is not about performance.

Neon's documentation: *"Neon uses PgBouncer in transaction mode
(`pool_mode=transaction`), which means connections are returned to the pool
after each transaction completes."* Among the features it lists as unsupported
through the pooler:

> Session-level advisory locks

**`manage.py predeploy` takes a session-level advisory lock**, so that two
rollouts cannot migrate at once. Its own docstring says so: *"Session-scoped,
so it is released when the connection closes — including when the process is
killed."*

Over a pooled connection that lock is granted and held by nothing. Each
statement can land on a different backend, `pg_try_advisory_lock` returns true,
and a second deploy is told it may proceed. **Losing it quietly is worse than
never having it**, because the docstring still claims it is there.

Neon's own guidance agrees, for its own reasons:

> Schema migrations | Direct | Tools may not support transaction pooling

So:

| What | Which string |
|---|---|
| `api` and `worker` containers | **pooled** |
| `manage.py predeploy` | **direct** — the host without `-pooler` |
| `manage.py check_database` | either; it takes no locks |

**`predeploy` now enforces this itself.** After the lock is granted it asks
`pg_locks` whether this backend actually holds it, and refuses with an
explanation if not. Checked by asking rather than by looking for `-pooler` in
the hostname: that tests one provider's naming convention, and this tests the
property the lock needs.

---

## `pg_trgm`, which M12 handed over unverified

ADR-023's handover:

> `CREATE EXTENSION pg_trgm` is verified locally, not on Neon. It ran against a
> live Postgres for the first time in T7, as superuser `app`. A managed
> provider may not grant it.

**What Neon's documentation says**, checked rather than assumed:

- pg_trgm has its own page: *"Activate `pg_trgm` by running the
  `CREATE EXTENSION` statement in your Postgres client."*
- Extensions that need Neon to enable them are **named individually** —
  `pg_repack` (*"must first be enabled by Neon Support"*) and `pg_cron`.
  **pg_trgm is not among them.**
- The role a project is created with is a member of `neon_superuser`.

That lowers the risk a long way. **It does not close it**, because "documented
as supported" and "this role may install it in this project" are different
sentences, and only running it answers the second.

### Running it is one command

```bash
DATABASE_URL='postgresql://…neon.tech/neondb' python manage.py check_database
```

Written for exactly this. It reports the server, the role, and whether each
required extension is installed **and usable** — an extension present in
`pg_extension` but outside this role's `search_path` answers every catalogue
query with "function similarity(text, text) does not exist", which reads as a
code bug rather than a configuration one.

Where an extension is absent it asks whether this role *could* install it, by
creating it inside a transaction and rolling back. **It changes nothing**, and
a test asserts that.

**Run it before `predeploy`, not instead of it.** `catalog.0005_search_vector`
is `atomic = False` — `CREATE INDEX CONCURRENTLY` requires that — so a failure
part-way can leave an `INVALID` index that must be dropped by hand before a
retry. Finding out from a read-only check costs nothing; finding out from a
half-applied migration costs an incident.

---

## Staging is a branch, not a second project

Neon branches copy the database cheaply, which is why ADR-002 rated staging as
near-free under this option. A staging branch of production gives a database
with the same schema and the same extensions, which is the only way to test a
migration against something shaped like the thing it will run against.

**M13 T8 is not finished until that branch exists and `check_database` has been
run against it.** Everything above is preparation; the verification M12 asked
for is an act, not a document.

---

## What is still the owner's to do

1. Create the Neon account and project, in an EU region (architecture.md §3).
2. Take both connection strings — pooled and direct — and set them as described
   above.
3. Create a **staging branch** of the project.
4. Run `check_database` against the staging branch, then against production.
5. Enable **point-in-time recovery**. M14 T8 wants PITR *and* a weekly
   `pg_dump` to R2, on the grounds architecture.md §3.7 gives: *"a backup in
   the same account as the database is not a backup."*
