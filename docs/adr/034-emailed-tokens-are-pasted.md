# ADR-034 — Emailed tokens are pasted, not clicked

**Status:** accepted — implemented 2026-09-28. **§5 records one question for the
owner** (whether to move to real links, which needs a backend setting).
**Date:** 2026-09-28
**Decides:** how a verification or password-reset token gets from the email into
the API, given that the emails send a bare token and no URL
**Depends on:** CLAUDE.md invariant 9 (session cookies; nothing auth-related in
storage), ADR-006 (provoke every control), ADR-023 §1 (a decision is not a
control until something asserts it)

---

## Decision

**Both tokens are redeemed by pasting them into a field**, because that is what
the emails actually send. A token in `?token=` is still accepted and is still
never rendered; the field appears only when the URL carried nothing.

**Verification happens on a click, never on mount.**

**The copy says "token", not "link"**, in the three places it said "link" for
something the email does not contain.

---

## 1. The defect this answers

Two endpoints, two emails, and no way to use either.

`backend/apps/notifications/templates/email/verification/body.txt`:

> "Use this token to verify your email address:" — followed by the raw token.

`.../password_reset/body.txt` is the same shape. **Neither contains a URL**, and
there is no `SITE_URL`, `FRONTEND_URL` or equivalent anywhere in `backend/` to
build one from — checked, not assumed.

What that meant in the product:

| | Before |
|---|---|
| `POST /auth/verify-email/` | **No caller anywhere in the frontend.** The view, its serializer, its `verify_email` throttle scope and `api.verifyEmail` all existed. Nothing ever called it, and no page existed to |
| `/reset-password` | Refused every visit without `?token=` with a dead-end interstitial, "This link is incomplete". Since the email sends no link, **that was every real reset** |

The reset page's refusal was tested, and the test was faithful — it asserted the
interstitial appeared and the API was not called. **The page it described was
wrong.** This is worth recording on its own: a green test suite certified a flow
that could not be completed, because every assertion was about the page's own
behaviour and none was about whether a token could be redeemed.

Neither gap is a backend fault. The API is complete and correct.

---

## 2. Why paste, and not a link

A clickable link is the better experience and is **not available today**. It needs
the frontend's base URL in Django settings, plumbed to both templates, configured
per environment — a backend change with a new environment variable, which is §5
territory and a different batch. Recorded in §5 as the open question.

Given that, the options were:

| Option | Why not |
|---|---|
| **Add the setting and send links now** | The right end state. A backend change with a new env var, per-environment config and two template changes — out of scope for a frontend batch, and it needs the owner's decision on the variable's name and where it comes from in each environment |
| **Leave it** | The status quo: two features that cannot be completed and one email endpoint with no caller |
| **Paste field** | What shipped. Frontend-only, works with the emails exactly as they are, and keeps working unchanged if links arrive later — a link just means the field is not shown |

The paste path is not a stopgap that has to be removed. When links arrive, the
`?token=` branch is the link's branch and already exists; the field is what
someone falls back to when the link is mangled by their mail client, which is
common enough that most products keep both.

---

## 3. Why the URL token is not prefilled into the field

The obvious implementation is one field, prefilled from `?token=` when present.
**It would have broken a security property both pages already had.**

`reset-password/page.test.tsx` asserts the token from the query string appears
nowhere in `container.innerHTML` — *innerHTML*, not text, because the failure mode
is a `value=` attribute. A prefilled input is exactly that attribute. CLAUDE.md §6
forbids weakening a control to make a feature work, so the field is shown **only**
when the URL carried no token, and the pasted value lives in separate state from
the link value.

The distinction is real and not pedantic: a value someone typed is on screen
because they typed it; a value we copied out of the URL and echoed into an input is
us widening the window in which a token sitting in the address bar can also be
shoulder-read, screenshotted, or scraped by an extension reading form values.

**Both directions are provoked.** Showing the field on the link path fails a test
that exists for that seam; showing it *and* prefilling it fails the
innerHTML assertion as well. Without the first of those, "the token is nowhere in
the page" could have been satisfied by a page that simply stopped working.

---

## 4. Why verification is a click and not an effect

A verification token is single-use — `services.verify_email` consumes it under
`select_for_update` — so **every POST after the first one fails**.

An effect that verified on mount therefore reports "not valid" for a token that
verified perfectly, in three ordinary situations:

1. React's double-invoked effects in development.
2. A refresh.
3. A back-navigation to the page.

The button costs a person one click and nothing else, because the email sends no
link to click in the first place. Pinned by a test asserting nothing is posted
before the press, and provoked by adding the verify-on-render call.

---

## 5. The wording, and the open question

The pages said "link" three times: "We will email you a link to set a new one", a
"reset link is on its way", "a verification link is on its way". The reset
confirmation then offered "Back to sign in" — the one page the token is no use on.

Now "token", and both confirmations say where the token goes. **This is the part
that decides whether the flow is discoverable**: the field could exist and nobody
would find it.

**Open for the owner, not decided here:**

1. **Should the emails send links?** That is the backend change in §2 — a settings
   variable for the frontend's base URL, per environment. If yes, this ADR's
   `?token=` branch is already the destination and only the copy softens back
   toward "link".
2. **The backend's own copy still says "link".** `VerifyEmailView` answers *"That
   verification link is not valid."* — quoted from `backend/apps/accounts/views.py`.
   The page displays it verbatim, because it must not invent a reason the API
   deliberately refused to give. Changing it is a backend edit; flagged, not done.

---

## 6. The resend form, and why it is on this page

A failed verification is exactly where a fresh token is needed, and there was
**nowhere to get one** — `POST /auth/resend-verification/` also had no caller. A
new page for one field would have been a second dead end to navigate to, so the
form sits under an `<h2>` on `verify-email`.

It inherits the anti-enumeration rule the other two forms follow, and for the same
reason: `ResendVerificationView` answers 202 identically for an unknown address, an
already-verified one, and a genuine resend, so the confirmation must hold for all
three. Asserted the way `register` and `forgot-password` assert it — by rendering
two different addresses and requiring the markup to come out **byte-identical**
apart from the address, which fails if the page ever grows a branch here.

---

## Consequences

**Positive.** Two features that could not be completed now can be. One endpoint
gained its first caller. The security property that made the naive fix wrong is
intact and better tested than before, because the seam between the two states is
now asserted rather than implied.

**Negative.** Pasting a token is worse than clicking a link, and this ADR does not
pretend otherwise — it records why the link is not available and what it would
cost. The reset page also gained a field on a path where a person may not expect
one, which is the price of the state being reachable at all.

**Accessibility.** Both pages keep their `<h1>` in the Suspense fallback, which is
the whole prerendered document for a route using `useSearchParams`. The new page is
in `verify:a11y`'s sweep — 12 built pages now, up from 11 — and axe runs over its
paste, error and verified states. The token field is `autocomplete="off"`
deliberately: a single-use token is not something a password manager holds, and
offering to fill it would offer the previous one. That is asserted in the 3.3.8
test's expected values, so it cannot be changed silently.

**Security.** No new surface. The token still travels only to the API; the guard
against posting an empty token moved from render time to submit time, which is the
only place it can live once there is a field, and is provoked on both pages.

**Performance.** `/verify-email` prerenders as static content — confirmed in the
build output, not assumed — with the form on the client like every other auth page.

---

## Verification criteria

1. **Done.** 13 provocations, one per property, each confirmed to fail the test
   that claims to protect it. One initially read as a missed control and was a
   fault in the provocation, not the test: flipping the render condition without
   also prefilling the value leaves the field empty, so "the token is nowhere in
   the page" was right to pass. Split into two provocations, both caught.
2. **Done.** `npm test` — 43 files, 491 tests before the axe additions; `tsc`,
   `eslint`, `verify:css`, `verify:static` and `verify:a11y` all clean, the last
   three against a fresh production build.
3. **Done.** The prerendered `/verify-email` document carries its `<h1>` and no
   form, checked in `.next/server/app/verify-email.html`.
4. **Outstanding, needs a person:** an end-to-end pass with a real email — register,
   copy the token out of Mailpit, paste it, and confirm the account verifies; then
   the same for a reset. Nothing here has been run against the live API, only
   against recorded responses.

## Related

CLAUDE.md §6, invariant 9; ADR-006; ADR-023 §1; ADR-030 (3.3.8 Accessible
Authentication); `docs/specs/frontend-state-and-api.md`.
