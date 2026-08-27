# M14 — Observability & Launch

**Status:** unblocked half approved 2026-08-27 (T2–T4). T5–T10 blocked.
**Branch:** `feat/m14-observability`
**Depends on:** M13 platform work (for most of it), M11 email adapter (for alerts)

---

## 1. Objective

**You can be woken up and know what happened.**

architecture.md:1061 lists: Sentry across all three services with spend caps;
uptime monitors; business alerts (§3.7); backup and a **restore drill
executed**; runbooks; a launch checklist. Its deliverables are blunt —
production live, *a restore has actually been performed once*, and you can be
woken up and know what to do.

---

## 2. What exists, measured rather than assumed

| §3.7 row | State |
|---|---|
| Logs — structured JSON | **Built.** `apps/core/logging.py`, contextvar plus a log filter |
| Uptime — `/healthz` | **Built**, and smoke-checked against the release image in M13 T5 |
| Errors — Sentry | **Nothing.** Not in either tier, not in any dependency list |
| App metrics | **No `/metrics` endpoint** |
| Business alerts | **Nothing** |
| DB backups, restore drill | Nothing — both need a database that exists |

### 2.1 The `request_id` chain is one hop of three

§3.7 is specific: *"`request_id` propagated from Next.js → Django → Celery.
Without this, debugging is archaeology."*

**Only the middle hop exists.**

- Django generates one per request, keeps it in a `ContextVar`, and stamps it
  on every log record. That half is good.
- **The frontend never sends one.** `lib/api/client.ts` sets no header, so a
  browser action and the Django request it causes cannot be joined up.
- **Celery never receives one.** `config/celery.py` has no signal plumbing and
  no task module references it, so a task logs `-` where the id should be.

The consequence is exactly the one that line was written to prevent: a lesson
whose transcription fails cannot be traced back to the upload that started it.

This is the sixth instance of the pattern ADR-023 §1 names — a documented
control that was partly or never built.

### 2.2 The reliability control ADR-002 rates highest does not exist

ADR-002 §4 lists nightly entitlement reconciliation among controls that cost
nothing, and says of the section: *"An hour spent on the reconciliation job
buys more real reliability than $100/month of redundancy."*

`apps/entitlements/management/commands/` contains `billing.py` and nothing
else. The reconciliation job was never written.

---

## 3. The unblocked half — T2 to T4

Approved to build now. None of it needs a platform, an account, or a bill.

| # | Task | Why it does not need M13 | State |
|---|---|---|---|
| T2 | Close the `request_id` chain, both missing hops | Application code | **done** |
| T3 | Entitlement reconciliation, as a command | Application code | **done** |
| T4 | Business alerts on what T3 finds | Uses M11's email adapter | **done** |

**T4's scheduling is not blocked, and the first version of this spec said it
was.** It cited CLAUDE.md §11 #3 as unanswered. **ADR-001 §2.2 settled it** —
Beat embedded in the Celery worker at exactly one replica, with
`django-celery-beat` keeping the schedule in Postgres rather than in a local
file that invariant 5 forbids. §11 was never updated to strike the row, so it
read as open for eleven milestones; `CLAUDE.md` was corrected on 2026-08-27,
on ADR-001 §3's own instruction.

That matters here specifically, because ADR-001 §2.2 says `django-celery-beat`
*"lands with the first periodic task, not in M0"* — and **T4 is the first
periodic task.** So this milestone is where Beat actually gets wired.

What remains is a **§5 dependency approval** for `django-celery-beat`, not an
architectural decision. It brings models and migrations.

**Approved 2026-08-27, and wired in T4.** It brought three transitive
dependencies — `cron-descriptor`, `django-timezone-field`, `python-crontab` —
all pinned, and nineteen migrations of its own. Verified against the live
stack: Beat starts inside the worker, the schedule is a row in Postgres, and
nothing lands on local disk.

---

## 4. The blocked half — T5 to T10

| # | Task | Blocked on |
|---|---|---|
| T5 | Sentry in Django, Celery and Next.js; DSN from env; **spend cap** | account, §5 gate |
| T6 | `/metrics` or Sentry Insights — queue depth, transcription age, webhook lag | T5 |
| T7 | Uptime monitors on `/healthz`, both tiers | a deployment |
| T8 | Backups: Neon PITR **and** weekly `pg_dump` to R2 | M13 platform |
| T9 | **Restore drill, executed** | T8 |
| T10 | Runbooks beyond rollback; launch checklist; close-out | all |

**T8's two providers are the point, not belt-and-braces.** §3.7: *"A backup in
the same account as the database is not a backup."*

**T9 is the deliverable that cannot be faked.** §3.7 again: *"An untested
backup is a hope, not a strategy."* It is the one task in this milestone whose
completion is a fact about the world rather than about the repository.

---

## 5. Decisions this milestone will need

Not required for T2–T4; required before T5 onward.

| # | Question |
|---|---|
| 5.1 | **Sentry** — a new service and a spend cap is a billing decision. §5 gate |
| 5.2 | **Uptime monitor** — UptimeRobot or Better Stack; both have free tiers, both are §5 |
| 5.3 | ~~**`django-celery-beat` as a dependency**~~ — **answered yes, 2026-08-27.** Wired in T4 |
| 5.4 | ~~**Alert delivery**~~ — **answered:** email through M11's adapter, to `OPERATIONS_ALERT_EMAIL`. Empty by default; the job logs and sends nothing rather than guessing at an address |

---

## 6. Abuse cases — these become the first tests

1. A `request_id` supplied by a client is **not trusted verbatim** — it is
   sanitised or replaced, because it reaches log aggregation and a crafted one
   is log injection.
2. A missing or malformed `request_id` never breaks a request; the server
   generates one instead.
3. Reconciliation **reports and does not repair**. A job that silently fixes
   entitlement is a second writer, and invariant 3 has exactly one.
4. Reconciliation is read-only against a live database, provably — no writes,
   asserted.
5. An alert with nothing to report **sends nothing**. An alert that always
   fires is one nobody reads.
6. The alert names what it found without leaking who it belongs to — an email
   address in an alert is personal data in a mailbox nobody audits.
7. Reconciliation over a large dataset does not fan out per subscription.

---

## 6.1 What the abuse cases actually caught

Every control was provoked before it was believed, per ADR-006. Two of them
were not catching what their names claimed:

- **`test_the_worker_starts_beat` passed with `--beat` removed.** It read the
  whole compose service block, and the *comment* above the command says
  `--beat`. A test that passes on a comment guards a comment. Now reads the
  `command:` line alone.
- **`test_the_scheduled_path_resolves_to_a_real_task` passed while the schedule
  pointed at a task that did not exist.** It asserted a constant defined at the
  top of the test file rather than the schedule's own string. Now resolves
  every entry in `CELERY_BEAT_SCHEDULE` against the task registry.

Both were found by provocation, not by review.

---

## 7. Not in M14's unblocked half

- ~~**No scheduler wired without approval.**~~ Approved 2026-08-27 and wired in
  T4; the placement was never open (ADR-001 §2.2).
- **No Sentry**, no uptime monitors, no metrics endpoint — all need accounts.
- **No repair path in reconciliation.** §6 case 3.
- **No launch checklist.** It would be a checklist over a product with no
  catalogue surface, which is the frontend-ownership question (ADR-020 §2)
  arriving for the fourth time.
