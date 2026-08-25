# M11 — Discovery & Notifications

**Status:** complete. All eight tasks shipped; see `docs/STATUS.md`.
**Branch:** `feat/m11-discovery`
**Depends on:** M3 (catalogue, publication state), M2 (the two emails that already exist)

---

## 1. Objective

**A learner can find a course they did not know to look for, and the system can
tell them something happened without a person doing it.**

architecture.md:1050 names six objectives. Two of them — the accessibility pass
and mobile QA — are **out of scope**, on the owner's decision of 2026-08-25.
The frontend today is auth pages plus one lesson page: there is no catalogue,
course, or account surface to pass over. See §2.5.

---

## 2. Decisions to settle before T2

Five questions. Each has a recommendation; none is settled until the owner
answers.

> All five settled on the recommendation. ADR-020 records the reasoning.

### 2.1 Where the search vector lives

`SearchVectorField` on `Course`, GIN-indexed. Three ways to keep it current:

| Option | Cost |
|---|---|
| **A — updated in the publication service** | One place already owns course state transitions. Misses a title edit that does not go through it. |
| **B — database trigger** | Cannot drift. Logic in SQL, invisible to Python, and a migration nobody can test the way they test a service. |
| **C — computed per query, no stored column** | Nothing to keep current; no GIN index is usable, so it scans. Fine at 100 courses, not at 10,000. |

**Recommendation: A**, with the write concentrated in one function that every
title/description write path calls, and a test that a direct `Course.save()`
without it leaves the vector stale — so the limit is visible rather than
assumed. ADR-011's standing rule applies: a field that gains meaning gets every
writer re-audited in the same change.

### 2.2 How search results paginate

Cursor pagination orders by `(-created_at, -pk)`. **Relevance ranking cannot
use that cursor** — rank is a function of the query, so it is not a stored,
stable column to page on.

| Option | Cost |
|---|---|
| **A — page-number pagination for search only** | Offset drift on deep pages; a `COUNT` per request. Contradicts architecture.md:700, which puts page-number on "small admin lists". |
| **B — cursor on `(-rank, -pk)` computed per request** | Works only if rank is deterministic for a given query, and the cursor encodes the query. Fragile. |
| **C — cap results, no pagination** | Top 50 and stop. A curated catalogue of hundreds makes this honest rather than lazy. |

**Recommendation: C**, with the cap and its reason in the response. Search is
not a browse surface — the filters in T4 are. If the catalogue ever justifies
deep search paging, that is a measurement, not a guess.

### 2.3 How the trigram fallback composes with full-text search

architecture.md:1050 says "trigram fallback" and does not say when it fires.

**Recommendation:** trigram runs **only when full-text returns nothing**, not
unioned into every query. Unioning makes every search pay for both and lets a
fuzzy match outrank an exact one. The fallback exists for typos, and a typo is
the case where FTS returns zero rows.

### 2.4 What makes a course "related"

Not specified anywhere. **Recommendation:** same language, then shared
`skill_areas`, then same level, ranked in that order, excluding the course
itself, capped at 6.

Deliberately **not** "students who took this also took" — that needs
enrolment volume this product does not have yet, and a recommender trained on
ten enrolments recommends noise.

### 2.5 Email: how much of it is real in M11

Invariant 4 says every provider sits behind an adapter. **There is no email
adapter.** `accounts/views.py:70` and `:293` call Django's `send_mail`
directly, from a view, in the request path.

**Recommendation:** M11 builds the interface, a fake, and a Celery task, and
moves the two existing callers behind it. **Resend is not integrated** — same
trade M4, M5 and M6 made for billing, video and transcription, and for the same
reason: its rate limits and free-tier boundaries are facts this project does
not have, and §6 forbids inventing them. Real Resend lands with deployment.

---

## 3. Model sketch

**`Course.search_vector`** — `SearchVectorField(null=True)`, GIN index. Weights:
title `A`, `skill_areas` `B`, description `C`. Instructor name is deliberately
absent; searching for a person is a different feature with different privacy
questions.

**`pg_trgm`** — enabled by migration (`TrigramExtension`). A Postgres extension,
not a package, and nothing on the bill.

**No new model for notifications.** An `EmailMessage` audit table is tempting
and premature: the questions it would answer ("did this send?") belong to the
provider's own dashboard until a provider exists. Revisit when Resend does.

**Migration note:** invariant 14 — the GIN index is created
`CONCURRENTLY`, and the backfill of `search_vector` for existing rows is an
idempotent, chunked management command, not part of the migration.

---

## 4. Abuse cases — these become the first tests

1. Search returns **no** unpublished, draft or archived course, at any query.
   Positive twin: archiving a live course removes it from results.
2. Related courses surfaces nothing unpublished either — the same rule, a
   second reader, which is where it is most likely to be forgotten.
3. Search does not leak lesson bodies, instructor-private fields, or provider
   identifiers.
4. Filters cannot be combined to bypass publication scoping — swept over every
   filter, not spot-checked on one.
5. A pathological query (very long, hundreds of terms, control characters) is
   refused or bounded, not served.
6. Search is throttled. It is the most expensive anonymous endpoint in the
   product.
7. A transactional email is never sent to an address the account has not
   verified — **except** verification and password reset, which exist to reach
   an unconfirmed address and are a closed, named list. A withheld message is
   skipped and logged, never raised: a notification may decline to go out, it
   may not take down the action it reports. (ADR-021 §4.)
8. A retried email task **may** send twice, and nothing pretends otherwise.
   (Reworded at T8. Delivery is at-least-once: `acks_late` redelivers a task
   whose worker died after the provider accepted the message, and nothing can
   distinguish that from one that never ran. At-most-once needs either the
   table ADR-020 §8 declined or a provider idempotency key that does not exist
   yet. `TestCaseEightIsNotMet` asserts the duplicate, because a missing test
   and a satisfied one look identical in a summary. ADR-021 §5.)
9. An email template never renders user-supplied content unescaped.
10. The search vector cannot be written from an API surface.

---

## 5. Task outline

| # | Task | Depends on |
|---|---|---|
| T1 | This spec + ADR-020 | five answers |
| T2 | `search_vector`, GIN, `pg_trgm`, backfill command | T1 |
| T3 | Search selector + endpoint, ranked and throttled | T2 |
| T4 | Filters: language, level, skill area | T2 |
| T5 | Related courses | T2 |
| T6 | Email adapter + fake + Celery task; move the two existing callers | T1 |
| T7 | The transactional set on top of T6 | T6 |
| T8 | Abuse cases, query counts, schema, types, ADR-021, close-out | all |

---

## 6. Not in M11

- **No accessibility pass, no mobile QA.** §1. There is no frontend to apply
  them to, and ADR-020 records who owns that gap so M12's Playwright journeys
  do not hit it a second time — M7 already flagged it once.
- **No Elasticsearch or Meilisearch.** architecture.md:1051 names reaching for
  one as the common mistake here, and a §5 approval gate stands in front of it
  regardless.
- **No Resend integration.** §2.5.
- **No recommender.** §2.4.
- **No email audit table.** §3.
