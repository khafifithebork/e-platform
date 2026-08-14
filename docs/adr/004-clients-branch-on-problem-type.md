# ADR-004 — Clients branch on the problem type, not the status code

**Status:** Accepted
**Date:** 2026-08-14
**Related:** `docs/architecture.md` §6.1, §6.3, §4.5 · `CLAUDE.md` §4.9 · ADR-001 §2.1

---

## 1. Context

`docs/architecture.md` §6.1 states: "`403` for authenticated-but-forbidden,
`401` for unauthenticated". The code does not do that, and cannot without
changing the auth strategy.

DRF raises `NotAuthenticated` with status 401, then downgrades it to **403**
whenever no authenticator supplies a `WWW-Authenticate` header.
`SessionAuthentication` supplies none — correctly, since there is no challenge
scheme to name. So an anonymous request and a genuinely forbidden one arrive at
the client as the same status code, with nothing to tell them apart.

That distinction is not cosmetic. §4.5 is explicit that the frontend must not
re-derive access rules, and the UI has to choose between "log in", "start
trial", "your payment failed" and "upgrade". A status code cannot carry that,
and M4 will need to express far more than two cases.

This was found while building the M1 exception handler, when an integration
test of deny-by-default returned 403 where the document promised 401.

## 2. Decision

**Keep DRF's 403. Clients branch on the RFC 9457 `type` member.**

Every problem document carries a `type` URI. Where a more specific type exists
it names the problem; otherwise it stays `about:blank`, which RFC 9457 §4.2.1
defines as meaning "the title is simply the status phrase".

Types are relative URI references under `/problems/`. RFC 9457 permits relative
references, and using them avoids baking a hostname into the API contract
before the domain is settled.

When a document carries a specific type, its `title` describes that type rather
than the status phrase, as RFC 9457 §3.1.1 requires.

## 3. Options considered

**A — Custom `SessionAuthentication` with `authenticate_header()`**, restoring a
literal 401. Rejected. It matches the document, but a `WWW-Authenticate`
response header can make a browser present its own basic-auth dialog, which is
an ugly failure mode on a cookie-session app. More importantly it solves only
this one distinction: 401-versus-403 says nothing about *why* access was
refused, so M4 would need the type mechanism anyway and we would be maintaining
two mechanisms instead of one.

**B — Branch on the problem type.** Chosen. One mechanism serves both the auth
distinction now and entitlement reasons in M4, and it is what RFC 9457 exists
for.

**C — Amend `architecture.md` §6.1 to say 403.** Rejected on its own, though
the document should be annotated. It is the cheapest option and it discards a
distinction the product genuinely needs.

## 4. Consequences

The `type` URI becomes part of the API contract. Renaming one is a breaking
change for any client branching on it, so the set is kept small and deliberate,
and lives in one place — `apps/core/exceptions.py`.

M4 gains its extension point for free. `EntitlementDenied` will set a
`problem_type` attribute and add extension members for `reason` and `cta`; the
handler already prefers an explicit `problem_type` over the default mapping, so
no change to the handler is required.

The status code alone is no longer sufficient for the frontend to decide what
to render. That is the point, but it must be stated plainly: **a client that
branches only on status will treat "log in" and "not allowed" identically.**

`docs/architecture.md` §6.1 now disagrees with the implementation. Per
`CLAUDE.md` §2 later ADRs beat earlier documents, and this ADR is that record.
The design document is not edited, for the reason given in ADR-003 §4.

**Not decided here:** whether `/problems/*` URIs should eventually resolve to
human-readable documentation. They are identifiers first; making them
dereferenceable is an option, not an obligation.
