# ADR-026 — The learner surface

**Status:** accepted
**Date:** 2026-08-29
**Milestone:** M16
**Builds on:** ADR-024 (how the public catalogue stays static), ADR-025 (B-lite)

---

## Context

M7 built the entire learning API in April — gated lessons, progress,
completion, playback tokens, transcripts, enrolments — and **nothing ever
called any of it.** M15 gave the product a public face; a visitor could browse
the catalogue, read a course outline, and reach a dead end.

M16 connected it. Four decisions are worth recording, because each one someone
would otherwise re-argue, and three of them were forced by constraints that are
not obvious from the code.

---

## Decision 1 — the lesson URL, and building the route that was specified

**`/courses/{slug}/lessons/{lesson_slug}` — and the backend route to match.**

`architecture.md` §6.2 line 743 specified `courses/{slug}/lessons/{lesson_slug}/`
at M0. It was never built; M7 shipped `/lessons/{id}/` instead.

**The schema had been shaped for it the whole time.** ADR-007 §1 put a
*redundant* `course` foreign key on `Lesson` for exactly one stated reason —
that this URL "resolves to one lesson only if the slug is unique per course" —
backed by `lesson_slug_unique_per_course`. Until M16 that constraint guarded a
URL nothing served.

**The hazard, which has its own test:** overriding DRF's `get_object` for a
two-field lookup **skips the base implementation's call to
`check_object_permissions`**. Forgetting that one line yields a route that
serves every lesson body to anybody who can guess a slug, while every other
test in the file still passes.

**One deviation from architecture.md, deliberately.** Its table lists this under
"Catalogue — `/api/v1/`", but that table predates the `catalogue/` prefix, which
`public_urls.py` introduced so that "the boundary between 'anyone may read this'
and 'only the owner may' is visible in the URL". This route serves gated
content, so it is mounted at the API root; behind that prefix it would make the
prefix lie.

---

## Decision 2 — personalisation on statically generated pages

**Client components, resolving after hydration, from a neutral initial state.**

Invariant 15 keeps the `(marketing)` group static: one HTML file, built before
any of these learners existed, served to everyone. Three things on those pages
are nevertheless personal — the header's account menu, and the progress strip
on a course page.

They resolve in the browser. The prerendered HTML stays identical for everyone,
which is what keeps §11 #5 moot under B-lite (ADR-025): no Server Component
reaches Django, so nothing crosses the public internet from Workers to Hetzner.

**Two properties this shape must have, and both were got wrong first:**

- **Start from *unknown*, not from signed-out.** Rendering the signed-out state
  as a placeholder flashes "Sign in" at every subscriber on every page load,
  and reads as having been logged out.
- **A 403 is an answer, not a failure.** `/auth/me/` and `/me/courses/` refuse
  anonymous callers, which is how these components learn nobody is signed in.
  Treating it as an error leaves the header stuck for the majority of visitors
  to a public catalogue.

**The course-page progress strip renders nothing in three of its four states** —
resolving, anonymous, enrolled elsewhere. That is the design: it is
supplementary detail on a page complete without it, and an error strip on the
busiest page in the product would be worse than silence.

---

## Decision 3 — six refusals, enforced by the type system

**`resolve_access` returns a reason, never a boolean (invariant 3), and the
interface says six different things.**

`LessonPlayer` had carried its own denial table since M7, keyed on
`SUBSCRIPTION_PAST_DUE` and `NOT_AUTHENTICATED` — **neither of which has ever
been a `Reason`.** Two branches that could not fire, four real refusals with no
branch at all, including `LOGIN_REQUIRED`, which is what every signed-out
visitor gets.

Nothing caught it because the codes were plain strings on both sides. The
serializers now use `ChoiceField`, so the schema carries `ReasonEnum`,
`openapi-typescript` generates a union, and the message table is
`Record<DenialReason, Refusal>` — **a missing reason is a compile error.** M8
and M9 will add reasons; this is what stops them shipping unhandled.

**`GRACE_PERIOD_ENDED` has no action link**, and that is the interesting one.
The person is a paying customer whose payment failed; the only useful
destination is a billing page, and there is none until M8. Telling them to
subscribe would be telling them to buy what they already bought.

Every other refusal points at `/pricing`, which says pricing is not announced
(§11 #1). A payment page that cannot take payment is not a placeholder.

---

## Decision 4 — one shell, and the landmark that owns it

**`SiteShell` is shared by `(marketing)` and `(learner)`.**

The learner pages had no layout at all. `(learner)` was created at T3 for the
lesson route and gained "my courses" at T5, and **neither task noticed** — so a
learner who followed "My courses" out of the header arrived at a page with no
header, no footer, no navigation and no skip link. Browser-back was the only
way out.

It was invisible from the source, because nothing was wrong in any file: each
page rendered exactly what it said it would. It showed up in the *built HTML*,
where the whole document read "My courses · Lingua / My courses / Loading your
courses…".

Adding the shell then gave every learner page **two `<main>` landmarks**, which
`verify:a11y` caught on the built output within a minute. That check only sees
statically generated pages, though, and the lesson route is dynamic — so a
source-level guard covers the group as well.

---

## Consequences

- **The lesson page is the only dynamic route in the product**, and
  `verify:a11y` cannot see it. Structural properties there are guarded by
  source-level checks and component tests instead.
- **`/me/courses/` gained `last_lesson_slug` and `next_lesson_slug`.** T3's URL
  change silently broke resume — the payload carried only UUIDs, and a lesson
  URL needs slugs. The ids stay: progress and completion are addressed by id.
  Both slugs come from correlated subqueries **ordered identically to the id
  they accompany**; sorted differently, the interface would link to one lesson
  while recording progress against another. Still 3 queries for one enrolment
  or ten.
- **`src/test/source.ts` exists** because the same mistake was made four times:
  a structural check grepping source, failing against correct code, because the
  file documented the rule it was being checked for. Comments are stripped in
  one place now.

---

## What M16 did not do

- **No account settings.** Profile, email change and subscription management
  touch flows M8 will rewrite.
- **No instructor UI.** The API exists and still has no caller.
- **No subscribe flow.** There is nothing to subscribe to.
- **No player redesign.** It was wired up as it stood, and it largely worked:
  eleven tests, ten passing first time.

---

## A note on what testing untested code actually found

The player and the transcript panel were written at M7 and never executed —
there was no runner until M15 T2 and no route to them until M16 T3. Between
them they passed thirty of thirty-three tests first time.

**The failures were mostly in the tests, not the code.** One asserted a
timestamp format that did not exist; one asserted a boundary at a moment that
falls in a gap between cues and proves nothing; one grepped a docstring.

The one substantive finding was the opposite of a bug: **`readyRef` is not the
guard its comment claims.** The source credits it with preventing a playhead of
zero being written over a real bookmark, and says this was watched happening.
Removing it entirely leaves every test passing, because `worthSending` already
refuses a beat with nothing watched and nowhere reached, and nothing can be
watched before the fetch returns — `loading` gates the play button out of the
DOM. It stays as defence in depth, and its test now says what is true rather
than claiming to prove something it cannot.
