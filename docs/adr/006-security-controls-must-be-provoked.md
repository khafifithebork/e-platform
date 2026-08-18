# ADR-006 — Security controls are tested by provoking them

**Status:** Accepted
**Date:** 2026-08-17
**Related:** `CLAUDE.md` §6, §8 · `docs/specs/m2-authentication.md` · `docs/adr/005-m2-authentication-decisions.md`

---

## 1. Context

M2 shipped two protective controls that were configured correctly, read
correctly in review, logged nothing unusual, and **did nothing at all**.

**The brute-force lockout (T5).** `django-axes` was installed, the middleware
was ordered correctly, `AXES_FAILURE_LIMIT` was 5 and `AXES_LOCKOUT_PARAMETERS`
was `[["username", "ip_address"]]`. But axes reads the username from
`request.POST`, which is empty for an `application/json` body, so every failed
attempt was recorded with `username=None`. The lockout looked up a real address
and matched nothing. Five wrong passwords followed by the right one returned
200. The `AccessAttempt` table filled up the whole time.

**The per-endpoint rate limits (T8).** Every auth view declared a
`throttle_scope`, and every scope had a rate matching `architecture.md` §6.4.
But `throttle_scope` is an attribute nothing reads unless `ScopedRateThrottle`
is in `DEFAULT_THROTTLE_CLASSES`, and it was not. The only limit in force was
the general anonymous one — six times more permissive than the login rate it
appeared to be replacing.

Neither was found by review, by a type checker, or by any functional test. Both
were found by a test that tried to trip the control and observed that it did
not trip.

The two failures share a shape worth naming: **a security control that is
absent fails loudly, and a security control that is inert fails silently.** The
second is more dangerous precisely because everything about it looks right.

## 2. Decision

**A control that protects something is not done until a test has provoked it
and observed it fire.**

Concretely, for anything protective:

- Assert the **behaviour**, not the configuration. `settings.AXES_FAILURE_LIMIT
  == 5` is not a test of a lockout. Six failed logins followed by a refused
  correct one is.
- Where a bypass is plausible, test the bypass. The lockout test changes the
  `User-Agent` on every attempt, because a lockout keyed on anything the
  attacker controls is theatre.
- Configuration assertions are still worth writing, but only **alongside** a
  behavioural test, never instead of one. They pin a value someone might loosen;
  they do not prove it is read.

This applies to: authentication and lockout, rate limits, permission classes,
entitlement decisions, webhook signature verification, and any check whose
failure mode is "allows something it should not".

It does not apply to configuration with no protective role — a page size, a log
level, a cache backend.

## 3. Consequences

**M4 and M8 are where this pays for itself.** The entitlement resolver and the
billing webhook handler are, per `CLAUDE.md` §8, the two places demanding 100%
branch coverage. An inert entitlement check gives the product away; an inert
signature check makes the webhook endpoint a free-subscription API. Both would
look exactly as correct in review as the two controls above did.

Some of these tests are slow and unpleasant to write — provoking a throttle
means making real requests until it fires, and provoking a lockout means
deliberately failing to authenticate. That cost is accepted.

Tests that provoke a control must not weaken it to do so. Raising a limit for a
*different* suite's convenience is fine; raising it in the test that is meant to
prove it works is not, and `CLAUDE.md` §6 already forbids weakening a control to
make a test pass.

## 4. Smaller decisions settled during M2

Recorded here rather than as separate ADRs, following ADR-005's precedent.

### 4.1 A CSRF bootstrap endpoint

`GET /api/v1/auth/csrf/` sets the CSRF cookie and returns nothing else.

Login is deliberately **not** CSRF-exempt: forcing a victim's browser to sign in
as the attacker is a real attack, and every action they take afterwards is
recorded against the wrong account. But Django only sets the cookie when a view
asks for it, so a first-time visitor has no token and cannot post the login form
at all. The endpoint closes that gap.

It is a plain Django view, outside DRF's deny-by-default and outside the
throttles, because it grants nothing and reveals nothing.

### 4.2 No web fonts

`create-next-app` wires up Geist via `next/font/google`, which makes every build
reach `fonts.googleapis.com`. When it cannot — as on the development machine
here — the build **warns and silently substitutes a fallback**, so the font that
was tested is not the font that shipped.

The project uses a system stack for both the UI face and the editorial display
face. If a licensed brand face is adopted later, self-host it with
`next/font/local` rather than reintroducing a network dependency at build time.
