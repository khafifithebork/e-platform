# STATUS

**Last updated:** 2026-08-12
**Updated by:** agent session (docs reorganisation, ADR-001, M0 plan — no code written)

---

## Current milestone

**M0 — Planning & Foundations.** Plan produced, awaiting approval. No implementation started.

---

## Completed

- **Documentation reorganised** into `docs/` and untracked. `docs/` is gitignored; the files remain on disk. `CLAUDE.md` stays at the repository root because the agent tooling loads it from there.

  | Was | Now |
  |---|---|
  | `phase-1-architecture.md` | `docs/architecture.md` |
  | `deployment-strategy.md` | `docs/deployment-strategy.md` |
  | `adr-002-cost-reliability-streaming.md` | `docs/adr/002-cost-reliability-streaming.md` |
  | `agent-prompts.md` | `docs/prompts/agent-prompts.md` |

  This makes the paths in `CLAUDE.md` §2 correct for the first time. The removals are staged in git but **not committed**.

- **`.gitignore` created** — `docs/`, `.env`, `.env.*` with `!.env.example`. The full ignore file lands with M0 task T1.
- **`docs/adr/001-architecture.md` written** — records the four settled decisions (same-origin routing, Celery Beat placement, hosting deferral, ASGI) and restates the payment provider as open with a standing "do not model billing" instruction.
- **M0 plan produced** — 11 tasks, ordered, with dependencies and invariant mapping. Awaiting approval.

Still no application code, no dependencies, no migrations, no tests. `backend/`, `frontend/`, `infra/`, `scripts/`, `.github/` do not exist.

---

## In progress

None. Blocked on approval of the M0 plan and the version matrix (below).

---

## Blockers

### Blocking the first M0 task

1. **Version matrix not agreed.** `pyproject.toml` and `docker-compose.yml` cannot be pinned without Python, Django, Node, Next.js, PostgreSQL and Redis versions. Proposed defaults are in the M0 plan §8; they need confirming or correcting.
2. **Dependency approval.** `CLAUDE.md` §5 requires approval for every dependency. M0 needs roughly nine runtime and six dev packages. The list is in the M0 plan §8. Decide once whether `docs/architecture.md` counts as a standing allowlist, or this recurs every milestone.

### Open decisions (`CLAUDE.md` §11)

| # | Decision | State |
|---|---|---|
| 1 | Payment provider & jurisdiction | **Open.** Blocks M4 schema and M8. Does not block M0–M3. Standing rule: do not model billing. |
| 2 | Same-origin routing | **Settled** — ADR-001 §2.1. Next.js rewrites now, Cloudflare Worker before launch. |
| 3 | Celery Beat placement | **Settled** — ADR-001 §2.2. In-worker, single replica. `--beat` and `django-celery-beat` land with the first periodic task, not in M0. |
| 4 | Hosting target | **Settled as deferred** — ADR-001 §2.3. Containerise for both; decide at M13. |
| 5 | Live classes on the roadmap | **Open.** Blocks nothing until M5. |

`CLAUDE.md` §11 still lists 2, 3 and 4 as open and should be updated.

### New questions raised by ADR-001, deliberately left open

- **BFF vs path routing (M2).** `architecture.md` §3.2 and §4.3 describe two different architectures as if interchangeable. Resolve at M2 kickoff, before auth flows are written.
- **Private network under B-lite (M13).** Server Components fetching Django "over the private network" does not hold if Next.js is on Cloudflare Workers and Django is on Hetzner.

### Documentation defects, not yet corrected in source

- `docs/deployment-strategy.md` §9.3/§14 total the recommended (Mux) stack at ~$62; the line items sum to ~$43. The $62 figure models Cloudflare Stream.
- `docs/adr/002-...` §7.1 audio-mode saving computes to ~$612, not ~$570; §5 B-HA column sums to $152, not $157, and mixes Scenario 1 and Scenario 2 figures.
- Neon is modelled at $15 throughout, against the documents' own derivation of ~$19–20.
- Mux's 1/10 audio rate is claimed for a playback *mode*; it appears to apply to audio-only *assets*. Untagged and unsourced — verify before budgeting.
- `Brainstormv1.md` is cited by section throughout `deployment-strategy.md` and is not in the repository.

---

## Next action

1. Approve, amend or reject the M0 plan.
2. Confirm the version matrix and the M0 dependency list (M0 plan §8).
3. Then begin M0 task **T1 — repository skeleton**, following `CLAUDE.md` §7.

Optional, and worth deciding now: whether to commit the staged doc removals, and whether `docs/adr/` should be tracked after all — ADR-001 is the durable record of decisions and is currently ignored.
