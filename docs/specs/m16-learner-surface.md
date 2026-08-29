# M16 — Learner surface

**Status:** complete 2026-08-29. Four decisions answered up front (§5). ADR-026.
**Branch:** `feat/m16-learner-surface`
**Depends on:** M7 (learning API), M4 (entitlements), M15 (the catalogue to enter from)

---

## 1. Objective

**A subscriber can find a lesson, watch it, and come back to where they left
off.**

M7 built all of that as an API in April and nothing has ever called it. M15
gave the product a public face; a visitor can now browse the catalogue, read a
course outline, and then reach a dead end — there is no link from a course to
its lessons, and no page that lists what they are part-way through.

---

## 2. What exists, measured rather than assumed

### 2.1 The learner API is complete and uncalled

| Endpoint | Built |
|---|---|
| `GET /api/v1/lessons/{id}/` — gated lesson | M7 |
| `GET|PUT /api/v1/lessons/{id}/progress/` | M7 |
| `POST /api/v1/lessons/{id}/complete/` | M7 |
| `POST /api/v1/lessons/{id}/playback-token/` | M5 |
| `GET /api/v1/lessons/{id}/transcript/` | M6 |
| `GET /api/v1/me/courses/` | M7 |

`Enrollment` already carries everything a "my courses" page needs —
`course_slug`, `course_title`, `last_lesson`, `next_lesson`,
`completed_lesson_count`, `lesson_count`, `last_activity`. Nothing new is
needed on the backend for §3's tasks.

**There is no enrolment endpoint, and that is deliberate.**
`learning.services` enrols on first contact with progress: *"Remember where to
resume, enrolling on first contact."* A learner enrols by starting a lesson.

### 2.2 The player exists and is unreachable

`LessonPlayer` and `TranscriptPanel` were written in M7. `/learn/[lessonId]`
renders the player. **Nothing links to it.** The page's own docstring says why:

> *"Addressed by lesson id rather than `/courses/{slug}/lessons/{slug}`,
> because that is how the API addresses a lesson and there is no course page yet
> to link from. The nicer URL belongs with the catalogue pages."*

M15 built the course page. That question is now live — see §4.1.

Neither component has ever been tested. There was no runner until M15 T2;
`heartbeat.ts`, the arithmetic underneath the player, was tested then and is
the only part that has been.

### 2.3 The entitlement resolver already says exactly why

`resolver.py` returns a *reason*, never a bare boolean — invariant 3. There are
**six distinct refusals** and three calls to action:

| Reason | CTA |
|---|---|
| `LOGIN_REQUIRED` | log in |
| `NO_SUBSCRIPTION` | subscribe |
| `SUBSCRIPTION_EXPIRED` | subscribe |
| `TRIAL_EXPIRED` | subscribe |
| `TRIAL_SCOPE` | subscribe |
| `GRACE_PERIOD_ENDED` | update payment |

**Six messages, not one.** That distinction is the whole reason the resolver
returns a reason, and collapsing it into a generic paywall throws away the work
M4 did.

`/auth/me/` returns an `Access` object too, so the shell can know a learner's
subscription state without a second call.

---

## 3. Tasks

| # | Task | Blocked? |
|---|---|---|
| T1 | This spec | no |
| T2 | An authenticated shell: who you are, and a way out | no |
| T3 | Course page → lesson, and the lesson URL question | no |
| T4 | The six gated states, each with its own message | no |
| T5 | "My courses" — enrolments, progress, resume | no |
| T6 | The player wired end to end: heartbeat, resume, position | no |
| T7 | The transcript panel, and following along | no |
| T8 | Completion, and what it does to the course page | no |
| T9 | Accessibility pass, close-out, ADR | no |

**Nothing here is blocked.** That is unusual for this project and worth saying:
every dependency is merged, and none of it needs an account, a platform or a
bill.

---

## 4. The questions this raises

### 4.1 The lesson URL

`/learn/[lessonId]` is a UUID in the address bar. The page itself flags this as
provisional and says the nicer form belongs with the catalogue pages, which now
exist.

**Deferred to T3 with a bias toward `/courses/{slug}/{lessonSlug}`**, because
it is shareable, it survives a lesson being re-created, and it matches how
`PublicCourseViewSet` already addresses things — by slug, for exactly this
reason. The cost is a lookup by two slugs where the API takes an id, and T3
must establish whether the API supports that before committing.

**If it does not, the URL stays as it is.** Adding a backend endpoint to make a
URL prettier is not this milestone's business, and inventing one without asking
is what §5 forbids.

### 4.2 A signed-in header on a static page

The `(marketing)` group is statically generated and invariant 15 forbids it
depending on a live API call. **A header that says "Your courses" when you are
signed in cannot be baked into that HTML.**

**Decision, made here rather than deferred:** the auth-aware part of the header
is a client component with a *neutral* initial state — neither "sign in" nor a
name — that resolves after `/auth/me/` answers. Not the signed-out state as a
placeholder, because that flashes "Sign in" at somebody who is signed in, which
reads as having been logged out.

This keeps invariant 15 intact: the static HTML is identical for everyone, and
personalisation happens in the browser. It is the same shape M15's search uses
and for the same reason.

### 4.3 Nobody can subscribe

There is no self-serve subscription and no price (§11 #1). Every "subscribe"
CTA in §2.3 therefore points at `/pricing`, which says plainly that pricing is
not announced.

**That is not a placeholder to be replaced later — it is the honest state of
the product**, and M15's structural guards will fail the build if this
milestone starts promising a trial or naming a figure.

---

## 5. Decisions, answered 2026-08-28

| # | Question | Answer |
|---|---|---|
| 5.1 | Scope | **Learner surface only.** No account settings, no instructor UI. |
| 5.2 | The existing player | **Wire it up as it is.** Route to it, verify it works, fix what is broken. No redesign. |
| 5.3 | Gated states | **Honest refusal with the reason.** All six, each with its own message. |
| 5.4 | Data fetching | **Client-side**, like the existing auth pages. |

**5.4 has a consequence worth stating.** Server Components fetching Django
would give a faster first paint and would **un-moot §11 #5 immediately** —
under B-lite (ADR-025) that fetch crosses the public internet from Cloudflare
Workers to Hetzner and needs its own authentication. Client-side fetching keeps
that question closed, and keeps the session cookie where invariant 9 wants it.

**5.2 carries a risk that should be named.** `LessonPlayer` and
`TranscriptPanel` have never been executed by a test or reached by a user.
"Wire it up as it is" may well mean "find out what is broken", and T6 and T7
should be expected to fix rather than merely connect.

---

## 6. Abuse cases — these become the first tests

1. **A signed-out visitor reaching a gated lesson is told to sign in**, not
   shown the lesson, and not shown a generic error.
2. **A signed-in learner with no subscription sees a different message** from
   one whose subscription lapsed, and a different one again from one in a grace
   period that ended. Six refusals, six messages.
3. **A preview lesson plays for a visitor with no account at all.** The
   resolver allows it before it looks at a user; the UI must not add a check
   the backend does not have.
4. **The player never reports progress for a lesson it could not load.** A
   failed fetch followed by a heartbeat is a write about a lesson nobody
   watched.
5. **Progress survives a reload**, and resumes at the recorded position rather
   than at zero — the failure that silently un-completes somebody's course.
6. **"My courses" shows a learner only their own enrolments.** The endpoint is
   scoped; the UI must not accept an id from anywhere else.
7. **No page in the authed surface renders lesson content it was refused.** A
   403 is not an empty player.
8. **Nothing auth-related is written to `localStorage` or `sessionStorage`** —
   invariant 9, and a client-heavy milestone is where it would happen.

---

## 7. Not in M16

- **No account settings.** §5.1. Profile, email change and subscription
  management touch flows M8 will rewrite.
- **No instructor UI.** The API exists and has never had a caller; that is its
  own milestone.
- **No subscribe flow.** There is nothing to subscribe to (§4.3).
- **No player redesign.** §5.2.
- **No new backend endpoints** without asking, including for §4.1's URL.
