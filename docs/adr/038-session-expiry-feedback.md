# ADR-038 — Feedback when a confirmed browser session becomes signed out

**Status:** Accepted and implemented locally
**Date:** 2026-10-17
**Related:** ADR-004, ADR-005, frontend-roadmap D5, frontend-state-and-api §10

## Context

The owner chose an inline sign-in notice rather than an automatic redirect.
Django reports missing authentication but cannot distinguish expiry from revoked
sessions, deleted cookies or another tab signing out. A numeric 403 also represents
ordinary permission failures. Neither a guessed timeout nor every 403 can establish
that a previously confirmed session ended.

## Decision

Observe existing API responses in browser memory. A successful, parsed `/auth/me/`
response establishes the presentation state `confirmed`. A subsequent request
that began in that state can report `ended` only for `/problems/not-authenticated`
or an entitlement-denied problem whose reason is `LOGIN_REQUIRED`. Retain the
server's detail verbatim. Subscription refusals, CSRF, network and server errors
do not end this observation. The original response/error continues to its caller.

An anonymous visit starts neutral and never produces an expiry notice. The
notice heading is **Sign in to continue**, followed by the server's message and a
Sign in link; it must not assert an unproven cause such as timeout. It does not
retry a failed action, redirect automatically or make an access decision.

Each request carries an observation ticket. Sequence ordering prevents an older
refusal overwriting newer `/me` confirmation. An ended-session transition advances
an epoch so late successes cannot clear it. Only a fresh successful `/me` request
confirms recovery; arbitrary successful public/protected requests cannot do so.

Intentional login/logout begins a new epoch and resets the observation to neutral.
Requests begun during those operations are ineligible observations even if they
finish later. A `finally` releases suppression on success, refusal, parsing or
network failure. A later fresh `/me` can establish the server's current answer.
This changes neither login nor full-navigation logout behavior.

The store contains only a status and, when needed, the server's message. It contains
no user identity, credentials, access decision or timer. No browser storage is used.
Every mutation/subscription is browser-guarded and the server snapshot is always
neutral, preventing cross-request state on the server and hydration disagreement.
The UI subscribes to this presentation store; Django remains authoritative.

## Bounded delivery

The first approved six-file batch is the store and its tests, API integration and
its tests, this ADR and STATUS. It introduces no visible notice, provider or API
contract change. The separately approved UI batch mounts a notice in the shared
shell and synchronizes header/navigation presentation, using existing components.

## Presentation and recovery

`SessionExpiryNotice` sits inside the shared main landmark above the page/rail
row. It reuses the themed error Notice with its symbol and live announcement;
the 44px Sign in link sits outside the live region. Below `sm`, the action stacks
under the message. Long unbroken server text wraps without horizontal scrolling.
The notice renders no static/server HTML, never takes focus, and has no animation,
timer, dismissal or automatic navigation. Reduced-motion users receive the same
immediate state change. Login pages remain the existing recovery destination.

The header and site map both use `useCurrentUser`. A confirmed loss invalidates
pending identity requests and removes their signed-in destinations. Recovery
confirmation contains no identity: each mounted consumer resolves `/auth/me/`
afresh, showing the neutral placeholder until its own answer arrives. A generation
guard prevents pre-loss responses from restoring the old account. Intentional
logout preserves the disabled Signing out control until its full navigation.
No provider, identity cache, polling or browser persistence is introduced.

Already-loaded page content and local form values remain in place. This notice
does not erase every page's memory or authorize a failed operation; Django still
checks every request, and existing page-level refusals remain visible. Native
download/unload paths retain the limits below. Test fixtures reset the observation
between simulated browser visits while preserving all existing assertions.

## Limits and verification

Detection occurs when an existing API request receives a qualifying response.
There is no polling, cross-tab channel or guessed expiry deadline. Native export
downloads and best-effort unload beacons bypass the request helper and are not
observation sources. Existing lesson gates and server access checks remain intact.

Tests cover anonymous and confirmed sessions, exact problem discrimination,
concurrent refusals, old successes/refusals, intentional login/logout including
in-flight and failed operations, recovery, unsubscribe, storage and server isolation.
The full frontend suite, type/lint/build and static artifact gates remain required.
