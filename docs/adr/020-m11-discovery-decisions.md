# ADR-020 — M11 discovery: five decisions, and one the project still owes itself

**Status:** Accepted
**Date:** 2026-08-25
**Spec:** `docs/specs/m11-discovery.md`

---

## 1. M11 is backend-only, and the reason is not scheduling

**Decision.** M11 ships search, filters, related courses and the transactional
email set. The accessibility pass and mobile QA named in architecture.md:1050
are **out of scope**.

**Why.** There is nothing to pass over. The frontend is auth pages plus one
lesson page; no catalogue, course or account surface exists. An accessibility
pass over three pages would produce a green report that means nothing, and a
green report is worse than an absent one — it is the inert control ADR-006
describes, wearing a compliance badge.

**This is a scope reduction, recorded rather than absorbed.** §2 of the
milestone list still says M11 includes them. It does, when there is a frontend.

---

## 2. The decision this project still owes itself: who owns the frontend

**This is the reason M11 was scoped as option 3 rather than option 1.**

M7 flagged it once already: *"M12 asks for Playwright journeys over a UI that
is mostly not built; that work is currently unowned by any milestone."*
Nothing changed, and M11 has now hit the same wall from the other side.

**The shape of the problem.** Every milestone from M3 onward has built backend
capability with no surface: a catalogue nobody can browse, entitlements nobody
can see, transcripts nobody can read, an admin API with no admin UI. Each was
individually correct — §5 forbids working ahead, and building a UI before the
API it consumes is the definition of it. The aggregate is a product that cannot
be used and two later milestones (M11's polish, M12's journeys) whose
objectives assume it can.

**Three ways out, none of them mine to choose:**

| Option | Consequence |
|---|---|
| **A — a frontend milestone before M12** | Honest, and pushes M12–M14 back by whatever it takes. |
| **B — fold surfaces into each remaining milestone** | Spreads the cost; risks each milestone stopping at "enough UI to demo". |
| **C — ship backend-first deliberately and rewrite M11/M12's objectives** | Cheapest, and requires admitting the product is not launchable at M14. |

**Recorded, not decided.** This belongs in CLAUDE.md §11's open-decisions
table, which is the constitution and not a file an agent edits unasked. **The
owner should add it, or tell me to.** Until it is answered, M12's Playwright
objective is unbuildable and should not be started.

---

## 3. Search: a stored vector, updated in one function

**Decision.** `SearchVectorField` on `Course`, GIN-indexed, written by one
function that every title/description/skill-areas write path calls.

**Why not a database trigger.** It cannot drift, which is genuinely better —
and it puts the logic in SQL where no service test can see it and no reviewer
reading `services.py` will know it exists. This codebase has repeatedly been
bitten by controls that are real but invisible from the code that depends on
them; a trigger is that by construction.

**Why not per-query.** No GIN index is usable, so every search scans. Fine at a
hundred courses. The point of choosing now is that it is not fine later, and
changing it later means a migration on a populated table.

**The limit is made visible rather than assumed.** A test asserts that a direct
`Course.save()` bypassing the updater leaves the vector stale. That is ADR-011's
standing rule applied at the moment the field gains meaning: re-audit every
writer in the same change, and prove what happens when one is missed.

---

## 4. Search results are capped, not paginated

**Decision.** Top 50 by rank, no pagination, with the cap stated in the
response.

**Why this is a constraint and not a preference.** Relevance rank is a function
of the query. It is not a stored column, so cursor pagination — which this
codebase uses everywhere time-ordered — has nothing stable to page on. The
alternatives were page-number pagination, which contradicts
architecture.md:700 and pays a `COUNT` per request, or encoding the query into
a cursor over `(-rank, -pk)`, which is fragile in exactly the way a paginator
must not be.

**What makes the cap honest.** Search is not the browse surface; the filters in
T4 are. Nobody pages to result 200 of a curated catalogue of hundreds. If that
ever stops being true it is a measurement — ADR-009 — not a guess.

---

## 5. Trigram fires only when full-text returns nothing

**Decision.** Full-text first. If it returns zero rows, run the trigram query.
Not unioned.

**Why.** A union makes every search pay for both, and lets a fuzzy match
outrank an exact one — which is the failure users describe as "the search is
broken" without being able to say why. The fallback exists for typos, and a typo
is precisely the case where full-text returns nothing.

---

## 6. "Related" is a rule, not a model

**Decision.** Same language, then shared `skill_areas`, then same level. The
course itself excluded, capped at six.

**Why not collaborative filtering.** "Students who took this also took" needs
enrolment volume this product does not have. A recommender trained on ten
enrolments recommends noise, and noise on a course page reads as a broken
product rather than an empty one. The rule above is explainable, testable, and
correct on day one with three courses in the catalogue.

---

## 7. Email gets an adapter in M11; Resend does not arrive until deployment

**Decision.** Build the provider interface, a fake, and a Celery task. Move the
two existing callers behind it. Do not integrate Resend.

**The thing this fixes is a live invariant violation.** `accounts/views.py:70`
and `:293` call Django's `send_mail` directly — a provider used with no adapter
(invariant 4), from a view (invariant 2), synchronously in the request path
(which makes a user's registration latency a function of an SMTP handshake).
It has been that way since M2.

**Why it must be fixed before T7, not after.** T7 adds the rest of the
transactional set. Adding five more callers to the pattern and then fixing six
is strictly worse than fixing two and adding five correctly.

**Why not Resend now.** Its rate limits, free-tier boundary and retry semantics
are facts this project does not have, and §6 forbids inventing them —
"fabricated infrastructure facts have already cost this project one budgeting
error". Same trade M4 made for billing, M5 for video and M6 for
transcription, and it has been right three times.

---

## 8. No email audit table, yet

**Decision.** Nothing records what was sent.

**Why.** The question such a table answers — *did this actually send* — is the
provider's to answer, and there is no provider. A table built now would record
that a fake accepted a message, which is not the fact anybody will want. It
arrives with Resend, or it does not arrive.

`AuditLog` is not the place for it either. That table is the administrative
trail: who did what to whom. A verification email is not an administrative
action, and widening it to mean "things that happened" is how a narrow, useful
table becomes a wide, unqueryable one (ADR-018 §8).
