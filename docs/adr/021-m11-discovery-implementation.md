# ADR-021 — M11 discovery: what implementation settled

**Status:** Accepted
**Date:** 2026-08-25
**Spec:** `docs/specs/m11-discovery.md`
**Decisions before code:** `docs/adr/020-m11-discovery-decisions.md`

ADR-020 recorded five decisions before any of this was written. This records
what writing it changed, three bugs it found, and one correction to ADR-020
itself.

---

## 1. A correction to ADR-020 §7, which was wrong

ADR-020 §7 called M2's direct `send_mail` "a live invariant violation" of
invariant 4 — every provider behind an adapter.

**It was not.** The code it accused had already argued the opposite, in a
docstring: Django's email framework speaks SMTP, Mailpit serves SMTP locally
and Resend serves it in production, so no vendor HTTP API is being called and
invariant 4 is not engaged until one is. That argument holds. The ADR was
written without reading it.

What was genuinely wrong with those two call sites, and is what T6 fixed:

- **Synchronous in the request path.** A learner's registration latency was a
  function of an SMTP handshake.
- **T7 was about to add five more.** Five call sites that each know how to
  build and send a message is the shape that becomes a migration.

Recorded rather than quietly edited, because the failure mode is worth naming:
**an ADR that accuses existing code should quote what that code says for
itself.** The docstring was three lines long and directly on point.

---

## 2. Three bugs, each found by a test built so that only the rule could pass it

**The overlap counter scored one for everything.** Related courses ranked by
shared skill areas using a single `Case` with one `When` per area — and `Case`
returns the *first* branch that matches, so a course sharing five areas and one
sharing one both scored 1. Ranking by overlap was doing nothing.

**The search endpoint had an unauthenticated 500.** `?q=%00` reached the
driver, PostgreSQL text cannot hold a NUL byte, and nothing caught it. One
request, no account.

**A notification policy broke the operation it described.** Abuse case 7's
first implementation *raised* when an address was unverified, so an unverified
learner changing their password got a 500 from the notice about the change.

The first two were caught because the tests were constructed so nothing else
could produce the result: the weaker related-course candidate is deliberately
the *more recent* one, so recency alone would have put it first, and the abuse
case listed control characters rather than only long input. The third was
caught by the existing password-reset tests, which is the other kind of luck —
a suite dense enough that a new rule collides with something.

**The standing lesson, which is M11's:** a test whose fixture happens to order
correctly proves nothing. Build the case so the wrong implementation gives a
visibly wrong answer.

---

## 3. Search: capped, and the cap says so

Relevance rank is a function of the query, so cursor pagination — which this
codebase uses for everything time-ordered — has no stable column to page on.
Results are the top 50 and the response carries `limit` and `truncated`.

`websearch_to_tsquery`, not `to_tsquery`: it accepts quoted phrases and
`-exclusions` the way a person expects, and it never raises on malformed input.
`to_tsquery` turns an unbalanced parenthesis from a visitor into a 500.

The trigram fallback runs **only when full text returns nothing**. A union makes
every search pay for both and lets a fuzzy match outrank an exact one, which is
what people describe as "the search is broken" without being able to say why.

The threshold is `pg_trgm`'s own documented default rather than a number chosen
here. §6 forbids inventing provider behaviour, and a tuning constant invented
in a selector is that in miniature.

---

## 4. Abuse case 7 withholds; it does not refuse

**Decision.** A message outside the two exemptions is skipped and logged when
the address is unverified. It does not raise.

**Why the first version was wrong.** It raised, and a notification is secondary
to the thing it reports: an unverified learner changing their password got a
500 from the notice *about* the change, and an approval would have failed the
same way for an unverified instructor. A notification may decline to go out; it
may not take the action down with it.

**Why the silence is findable.** The decline is logged with the template name —
not the address, which is personal data — and the abuse-case tests assert an
empty outbox rather than trusting the log.

**The exemptions are a closed, named list**: `verification` and
`password_reset`. Verification exists to reach an unconfirmed address, and a
reset has to work for someone who never confirmed theirs or an unverified
account is unrecoverable rather than merely unverified. A test asserts the list
has exactly those two, so a third is a visible edit.

---

## 5. Abuse case 8 is unmet, deliberately, and asserted as such

**Delivery is at-least-once.** Celery with `acks_late` redelivers a task whose
worker died after the provider accepted the message, and nothing can tell that
apart from a task that never ran.

At-most-once needs either an idempotency table — ADR-020 §8 declined one,
because the question it answers belongs to a provider that does not exist yet —
or a provider-side idempotency key, which arrives with Resend.

**`TestCaseEightIsNotMet` asserts the duplicate**, and a second test asserts the
`notifications` app has no models at all. A missing test and a satisfied one
look identical in a summary; an asserted gap does not. The spec sentence is
reworded so the document stops claiming a guarantee the code does not make.

---

## 6. The search vector is written by a service, and the drift is pinned

ADR-020 §3 chose a service-written column over a database trigger. A trigger
cannot drift; this can. `test_a_direct_save_leaves_it_stale` provokes exactly
that and pins what happens, rather than leaving it as a footnote — and if it
ever starts failing, somebody added a trigger and this ADR needs rewriting.

Computed in the database rather than in Python: `to_tsvector` is Postgres's own
parser, and a Python reimplementation would drift from the one the query side
uses, so matching would depend on which half was edited last.

Written with `update()`, so `updated_at` does not move. Refreshing a derived
column is not an edit of the course.

---

## 7. Found in passing, not fixed: the catalogue has no instructor name

`PublicCourseSerializer.instructor_name` sources `instructor.get_full_name`.
**`User` has no such method**, and because the field is `read_only` DRF raises
`SkipField` rather than erroring — so the field is **silently absent from every
catalogue response**, and no test asserts it.

Underneath it is a product gap rather than a bug: **there is no instructor name
anywhere in the data model.** `display_name` lives on `StudentProfile`, which
an instructor need not have.

Not fixed here, because choosing what a public page shows in place of a name is
a product decision and inventing one is the §6 failure in a new costume. M11's
review email uses the instructor's address instead, which is honest for a
message addressed to administrators who already see addresses in diagnostics.

---

## 8. Carried out of M11

- **The frontend still has no owner** (ADR-020 §2). M11 dropped its
  accessibility pass and mobile QA for that reason, and M12's Playwright
  objective is unbuildable until it is answered. This is the second milestone
  to hit it.
- **The instructor name**, above.
- **Resend is not integrated**, by decision. The adapter it would replace sends
  real SMTP, so the swap may turn out to be configuration rather than code.
- **No GIN index on `skill_areas`.** A curated catalogue of hundreds does not
  need one, and adding an index nobody has measured a need for is the guess
  ADR-009 forbids. Revisit with a measurement, not a hunch.
- **`CREATE EXTENSION pg_trgm` is unverified on Neon.** The local container
  runs as a superuser; a managed provider may not grant it. M13.
