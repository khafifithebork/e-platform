# ADR-009 — Measure queries and constraints; do not reason about them

**Status:** Accepted
**Date:** 2026-08-18
**Context:** M3 — Catalogue domain. Companion to ADR-006, which made *provoking
a security control* the standard. This makes the same demand of performance and
database-behaviour claims.

---

## 1. The problem

ADR-006 exists because M2 shipped two security controls that were configured
correctly and did nothing. M3 produced three defects of the same shape, none of
them security:

| Claim I wrote | What was true |
|---|---|
| The bulk reorder needs the deferrable constraint to survive its intermediate state (T3) | `bulk_update` writes the permutation in one statement, and PostgreSQL checks a deferrable constraint at end of *statement* even when IMMEDIATE. It survived by batching. |
| The public catalogue list costs two queries — page plus count (T8) | One. Cursor pagination issues no `COUNT`, and a view with no authentication classes does no session lookup. |
| `courses_for_instructor` joins language and instructor because the list renders both — without it, two extra queries per row (T4) | Zero difference. The serializer emits them as primary keys, which come from the `_id` columns already on the row. The join widened every page and saved nothing. |

Each was written in a docstring, read as correct in review, and was false. None
would have failed a functional test. The common cause is not carelessness about
security — it is **reasoning about database behaviour instead of counting it**.

A wrong claim in a docstring is worse than no claim: the next person optimises
against it, or preserves a join that costs and buys nothing.

---

## 2. The rule

**Any statement about query count, index use, lock behaviour or constraint
timing must be produced by measuring, and the measurement must be committed as
a test.** If it is not worth a test, it is not worth asserting in a comment.

This is narrower than "write performance tests". It does not ask for
benchmarks. It asks that a claim of the form *"this avoids N queries"* or
*"this needs a deferred constraint"* be accompanied by the thing that would
fail if it stopped being true.

---

## 3. How to write a query-count test so it means something

`assert_num_queries(3)` over a fixture with one row proves a number and nothing
else. With one row, a fan-out costs exactly one query, so the test passes while
the endpoint is broken.

**Run the endpoint at two dataset sizes and assert the count is identical**,
then pin the absolute value:

```python
seed(1)
small = count_queries(url)
seed(9)
large = count_queries(url)

assert small == large, f"{url} fans out: {small} for 1 row, {large} for 10"
assert large == expected
```

The first assertion is what "does not fan out" actually means. The second stops
the number drifting upwards unnoticed.

Two details that decide whether it works:

- **Give each row a distinct related object.** Ten rows sharing one instructor
  are resolved once from Django's identity map, and the fan-out disappears.
- **Verify the test fails.** Remove the `select_related` and confirm the
  numbers diverge. Removing the review-trail join takes it from 5 queries at
  one row to 14 at ten; removing the catalogue join takes it from 3 to 21.
  A query-count test that has never been seen to fail is ADR-006's inert
  control wearing a different hat.

---

## 4. `select_related` only where a relation is dereferenced

A `select_related` is not free — it widens every row returned. Add it when
something actually reads through the relation:

- **Needed:** a nested serializer (`LanguageSerializer` inside the public
  course card), or an attribute read (`actor.email`, `instructor.get_full_name`).
- **Not needed:** a `PrimaryKeyRelatedField`. DRF reads `<field>_id` off the row.
- **Not the same thing:** ordering by a related column (`section__position`)
  produces a JOIN in the query plan, but not a `select_related`.

---

## 5. Constraint timing is invisible under test rollback

`pytest-django` wraps each test in a transaction that never commits, so a
`DEFERRABLE INITIALLY DEFERRED` constraint is **never checked**. A test
asserting that a deferred swap succeeds passes identically whether the
constraint defers or not, and would stay green if someone dropped `deferrable=`
from the migration.

Deferred constraints therefore need a **pair** of tests: one showing the
operation succeeds, and one under `SET CONSTRAINTS ALL IMMEDIATE` showing it
fails. The second is the one carrying the information.

Write the pair against the shape the constraint must actually tolerate. Testing
the endpoint proves less than testing a row-by-row swap, because the endpoint's
`bulk_update` avoids the intermediate state by accident.

---

## 6. Scope

Applies to every milestone from M3 onward. It bites hardest at:

- **M4** — the entitlement resolver runs on every content request; a fan-out
  there is a fan-out on the hottest path in the product.
- **M5/M7** — lesson lists with media and progress are the natural home of an
  N+1 per card.
- **M12** — hardening is where a wrong docstring gets trusted and the wrong
  thing gets optimised.

**Not a licence to optimise early.** The rule is about honesty, not speed:
measure before claiming, and delete the join you cannot justify with a number.
