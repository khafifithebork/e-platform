# STATUS

**Last updated:** 2026-09-27
**Updated by:** Claude Opus 5 (frontend redesign stages 2 to 4; the frontend audit,
its four ADRs, and the fixes that followed)

---

## The frontend audit — closed out, except what needs a person

**Eleven documents, four ADRs, and seven follow-up changes**, 2026-09-27 to
2026-09-28. The audit itself (**PR #75**) changed no application code; everything
after it did.

| PR | |
|---|---|
| #75 | The audit package — 11 documents, four ADRs proposed |
| #76 | ADR-030 and ADR-031 accepted |
| #77 | `color-scheme` declared |
| #78 | Inline-direction utilities made logical, with a pinned guard |
| #79 | Theme toggle declined, localisation deferred — all four accepted |
| #80 | WCAG 2.2 guards for 3.3.8 and 2.5.8 |
| #81 | Error and loading boundaries, reporting through the Sentry seam |
| #82 | STATUS: the outcome, and the four claims nobody has looked at |
| #83 | `/me/courses/` pagination — a learner past page one saw part of their list |
| #84–#87 | STATUS and the runbook: the audit's outcome, and the reduced-motion check confirmed |
| #88 | **2.4.11** — the focus ring could hide behind the fixed navigation toggle |
| #89 | Per-route bundle figures, measured |
| #90 | **`axe-core` adopted**, and the bug it found on its first run |

**One dependency was added, and it is worth being exact about.** `axe-core` as a
**devDependency**, approved by the owner under §5 on 2026-09-28 (PR #90). Zero
runtime dependencies were added, it has none of its own, and it appears in **zero
client chunks** — asserted against the built output. No service and no cost changed.

Everything before that PR was built with no new dependency at all, which is the more
useful fact: 45 dead token classes, three CI guards, error boundaries, pagination and
the 2.4.11 fix all needed nothing installed.

The frontend suite went from 416 tests across 35 files to **470 across 42**.

**There is no frontend work left that an agent can do alone.** Every remaining item
needs either a browser and a person, or backend work that is not scheduled:

| Remaining | Needs |
|---|---|
| The four unconfirmed claims below | A person with a browser. Minutes each |
| A2 — reproduce the 2.4.11 focus fault | The same. **The remedy cannot be scoped until it is reproduced** (ADR-006) |
| ~~A5 — per-route first-load JS~~ | **Done 2026-09-28**: 312–326 KB gz, routes nearly identical. A budget is now proposable — 350 KB gz per route — and enforcing it needs the owner |
| `<track>`'s `srclang` and `label` | The API to model caption language. Not knowable from the frontend |
| ~~B2 — the architecture.md §8.2 tooling discrepancy~~ | **Resolved 2026-09-28** — `axe-core` adopted, `MSW` and `Playwright` declined. Playwright worth revisiting at M8 |

**All four ADRs accepted by the owner on 2026-09-27, and two defects fixed in the
process.**

| ADR | Decision | Left to do |
|---|---|---|
| **ADR-030** | WCAG 2.2 AA. **Supersedes architecture.md's 2.1 AA baseline**, on the level only | **Nothing.** C3, C4 and D2 all done — **2.4.11 was the one real failure, and it is fixed** |
| **ADR-031** | Three boundary files, each reporting to Sentry | **D1 done 2026-09-27** — built, 11 tests, unverified in a browser |
| **ADR-032** | Theme follows the system; **manual toggle declined** | nothing. §2's defect fixed; A4 confirms it |
| **ADR-033** | Localisation **deferred** with a named trigger | §3's `<track>` gap, blocked on backend (D4) |

**Accepted is not built.** A decision being made means the work may be *planned* —
it does not skip CLAUDE.md §7, and D2 may still reopen a layout ADR-029 accepted.

**One practice from this round is worth keeping.** Both of the later ADRs were
*split* before being decided: each mixed "this is broken" with "what should we
do", and **the broken half never needed the decision.** ADR-032 §2
(`color-scheme`) and ADR-033 §2 (logical properties) shipped hours ahead of the
questions they had been sitting behind. When an ADR contains both, split it.

### Correct by reasoning, unconfirmed by eye — the thing to watch

**Three claims are believed on argument and a passing test. A fourth was confirmed**
— the owner checked reduced motion in Firefox on 2026-09-28, hero and
scroll-triggered sections both, and the landing page renders. That was the fault
that started this workstream, and it is the only item here established by a person
rather than argued from a test. Individually each is defensible; as a set it is the
largest risk this workstream carries, because the test count going up reads as
reassurance while this list quietly grows.

| Claim | Why no agent can close it |
|---|---|
| `color-scheme` fixed dark-mode scrollbars and autofill | A scrollbar's colours are not exposed to `getComputedStyle`, and autofill needs a real interaction |
| Logical properties flip under `dir="rtl"` | That browser does not re-resolve logical properties on a direction change — proven with an isolated inline-styled element, which also fails to flip |
| A learner hitting an error boundary gets a usable page | Inducing a real render error means changing code to break it |

Each is roadmap section A. **All four are minutes of work for a person with a
browser**, and three of the four are confirmations of fixes that shipped on
specification rather than observation.

**Closed 2026-09-28:** *the landing page is not blank for a reduced-motion visitor.*
Confirmed by the owner in Firefox — the hero on load, the course cards and four
panels on scroll. Worth keeping visible rather than deleting: it is the one claim in
this table that has ever been closed, and it took a person thirty seconds after four
days of being flagged.

**Why these three and not everything else untested by eye.** Most of this work is
logic a unit test exercises fully — D3's pagination has never been rendered in a
browser either, and that is fine, because jsdom can reach every branch of it. These
three are different in kind: **the property itself is invisible to the test
environment.** jsdom paints nothing, the pane freezes its own clock, and a scrollbar
has no API. No amount of additional testing closes them, which is why they are a
list to hand over rather than a backlog to work through.

**Three tooling artefacts in one session, each of which first read as a bug in the
code**: the frozen `requestAnimationFrame`, a stylesheet that had not loaded
reporting every border radius as `0px`, and the direction change above. Isolating
before concluding is what separated them — and in the last case, not doing so would
have cost a revert of a correct change.

### Seven defects — six fixed, one blocked

| Defect | State |
|---|---|
| **No error or loading boundaries anywhere** in `src/app`, so a render error showed Next's unstyled default page and what reached Sentry was whatever the framework did | **Fixed** 2026-09-27. Three boundaries, reporting through the one Sentry seam, and an assertion that no error message, digest or address reaches the DOM |
| **`/me/courses/` pagination ignored** — a learner past the first page saw part of their list with no indication more existed | **Fixed** 2026-09-27. Root cause was a hand-written response type omitting `next` (invariant 16). A "load more" control, and `next` is **not followed** — Django builds it from the internal host |
| **`color-scheme` never declared**, so dark mode kept light scrollbars and autofill — the latter can push text below the contrast `contrast.test.ts` certifies and cannot see | **Fixed** 2026-09-27, with a provoked test. Measurement corrected the ADR on the way: form-control boxes were never affected, because Tailwind's Preflight already resets them |
| **`<track>` lacks `srclang` and `label`** | **Blocked, not open** — the correct value is not knowable from the frontend because nothing models caption language. Backend work, roadmap D4. Hardcoding a guess would be wrong for exactly the courses that matter most |

Three more, each found by a different kind of looking — which is the useful pattern,
and the reason none of them could have been found by the others:

**By a grep: physical inline-direction utilities.** Fixed — six swapped to logical,
two pinned as navigation chrome ADR-029 owns. The ADR had estimated "about four";
counting properly found nine.

**By a person with a keyboard: 2.4.11 Focus Not Obscured.** The owner tabbed to a
control low on a page and watched the focus ring disappear behind the fixed "Site
map" button. Reproduced at 420×480 on `/courses` — three overlapping elements — and
fixed with `scroll-pb-20 xl:scroll-pb-0` on `<html>`, re-measured at zero. **Fixed
2026-09-28.**

The remedy is the first of ADR-030 §3's three candidates, not the third: the one that
would have reopened ADR-029's accepted layout was not needed, because the gap scroll
padding leaves — an element obscured without any scrolling — was already covered by
`SiteShell`'s footer padding.

**By a tool, within seconds of being installed: `role="alert"` on a `<ul>`.** `Field`
put the role on its list of error messages, and an explicit role *replaces* the
implicit one — so the list stopped being a list while still containing `<li>`
children with nothing to belong to. Reported as `aria-allowed-role` and `listitem`.
**Fixed 2026-09-28.**

The instructive part is that **`Field.test.tsx` passed before and after the fix.** It
asserted that a `role="alert"` element exists and contains the message, which was
true either way. Nothing already in this repository could have caught it — which is
the whole case for the dependency, and why the §5 approval was worth asking for.

**No defect is open work.** `<track>` is blocked on backend modelling rather than on
anyone's decision — the frontend cannot know what language a caption is in until the
API says.

The audit's own headline, worth recording because it shaped the package: **little
was wrong.** Pricing is `null` with a tripwire test rather than an invented number,
captions are already wired to the VTT projection, and the generated types,
problem-type branching, three-state auth pattern and static boundary are all
implemented and guarded. The package therefore records what exists and names four
narrow defects instead of proposing to rebuild working foundations.

**The first action was not a documentation task, and it is now half done.**
`docs/specs/frontend-roadmap.md` §A1: the owner opened `/` with reduced motion on in
Firefox on 2026-09-28 and the headline shows — settling the hydration half, which is
the half that had been outstanding since 2026-09-25. **Scrolling down closes the
rest**, because the sections below the hero use a different mechanism.

| File | What it is |
|---|---|
| `docs/adr/030-accessibility-wcag-22-aa.md` | Proposes WCAG 2.2 AA. Five of the six criteria 2.2 adds at AA appear already satisfied; **2.4.11 Focus Not Obscured is a real risk** below `xl` |
| `docs/adr/031-error-and-loading-boundaries.md` | Proposes three boundary files. **There are none in the tree today**, so a render error shows Next's default page and may never reach Sentry |
| `docs/adr/032-theme-system-only.md` | Proposes keeping the system theme and declining a toggle. Records a defect: **`color-scheme` is never declared** |
| `docs/adr/033-interface-and-learning-languages.md` | Names the four language axes, defers localisation, and records that `<track>` lacks `srclang`/`label` — which the API cannot yet supply |
| `docs/design-system.md` | Reference for tokens, the three component tiers, variants and states. Carries the two open design questions rather than settling them |
| `docs/specs/frontend-state-and-api.md` | State boundaries, problem-type handling, retry safety, and a **measured** bundle baseline |
| `docs/runbooks/accessibility-verification.md` | Automated versus human checks. **§3.1 partly walked 2026-09-28; nothing else** |
| `docs/frontend-principles.md` | Fourteen rules, each linked to its authority |
| `docs/design/figma-handoff.md` | A written structure. **No Figma file was created or modified** |
| `docs/specs/frontend-roadmap.md` | The remaining gaps in dependency order, **conditional on which ADRs are accepted**. Nothing in it jumps ahead of M14 |

**Two discrepancies are reported and deliberately unresolved**, per CLAUDE.md §2:

1. ~~architecture.md §8.2 names `MSW`, `@axe-core/react` and `Playwright`. None is
   installed.~~ **Resolved 2026-09-28.** The owner approved **`axe-core`** under §5
   and declined `MSW` and `Playwright`; §8.2 is revised with the reasoning and
   ADR-030 §5 records it. Not `@axe-core/react` — that logs to the console in
   development and fails nothing. Zero dependencies, and verified absent from the
   client bundle.

   **It found a real bug on the first run.** `Field` had `role="alert"` on its `<ul>`
   of error messages; an explicit role replaces the implicit one, so the list stopped
   being a list while still containing `<li>` children with nothing to belong to.
   `Field.test.tsx` passed before *and* after the fix, because it asserted an alert
   exists and contains the message — true either way. That is exactly the class of
   fault the structural greps cannot reach, and the argument for the dependency.
2. ~~architecture.md sets WCAG 2.1 AA; ADR-030 proposes 2.2.~~ **Resolved
   2026-09-27** — ADR-030 accepted, and it now carries a `Supersedes` line naming
   architecture.md's baseline so the older document cannot be read as current on
   the level.

**Documenting was not implementing, and then most of it got implemented.** The eleven
documents describe decisions and procedures; **six of the seven defects they surfaced
have since been fixed in code, each with provoked tests**, and the seventh is blocked
on the backend rather than on anyone here.

What remains genuinely undone is verification that needs a person:
`runbooks/accessibility-verification.md` has three rows in its log — §3.1 twice and
§3.2's 2.4.11 check — and §3.2's remaining keyboard pass, §3.3's screen reader, §3.4's
zoom and reflow and §3.5's forced colours have not been walked.

---

## Current milestone

**The approved frontend redesign is four stages in and the visual work is done.
No new product milestone is started.** ADR-029 records the Linglee reference and
scope. Stage 1 refreshed tokens, navigation, buttons and cards and gave mobile
keyboard navigation regression tests. Stages 2 and 3 landed as **PR #71**
(`85bbc42`); stage 4 as **PR #73** (`44e6ca0`).

**Stage 4 is the one worth reading, because none of it was a redesign.** It set
out as a composition pass over the learner surface and instead found that **45
utility classes across 15 components had never applied in any release** —
`rounded-[--radius-md]`, Tailwind 3's spelling, which Tailwind 4 compiles to an
invalid declaration the browser drops. This repository has been on `^4` since its
first frontend commit, so nothing that used it has ever rendered a radius or a
shadow. Everything in that stage was found by measuring the running app rather
than by reading code, and the measurements are in the sections below.

What stage 3 actually was is worth stating plainly, because its name is
misleading: **the auth pages were not visually redesigned.** Measuring before
planning, per ADR-023 §1, found them already consistent — stage 1 had given them
their two-column shell and they were already built from `Field`, `Notice` and
`Button`. What was missing was tests, and two of the nine untested states turned
out to carry a security control. The visual work in stage 3 is one component.

Verification, run and not assumed, on the merged tree rather than the branch:
**416 frontend tests across 35 files** (365 across 26 at the end of stage 1),
`tsc --noEmit` and ESLint clean, all four public routes prerender, 11 built pages
structurally sound, and the three `verify:*` scripts pass. CI green on both merge
commits.

**Three guards now run in CI that did not before**, and each exists because
something got through every check that already existed:

| Guard | Catches |
|---|---|
| `verify:css` (`scripts/assert-css-tokens.mjs`) | any declaration in the compiled CSS whose value is a bare custom-property name |
| `src/test/css-tokens.test.ts` | the Tailwind 3 bracket spelling in source, in a second, without a build |
| `src/components/ui/PageTitle.test.tsx` | any `<h1>` in `src/` that sizes itself by hand |

**Written as two unverified things; one has since been closed:**

- ~~The reduced-motion fix has never been seen working in a browser.~~ **Confirmed
  2026-09-28**, by the owner in Firefox: the headline on load, and the course cards
  and four panels on scroll. React's hydration error being gone was always verified;
  "the content becomes visible" was the separate claim, and it now holds for both
  mechanisms. The agent's browser could never have shown it — it reports
  `document.hidden` even when fronted, so `requestAnimationFrame` is frozen at zero
  frames per second and Motion cannot animate in it at all. **Re-check after any
  change to `MotionProvider`, `Reveal` or `StaggerList`.**
- **The backend suite has not been run since M14 T6**, and this one still stands.
  Nothing under `backend/` has changed across these stages, which is inference, not a
  run. The 1532 figure below is inherited.

**Two design questions are open and deliberately were not answered by whoever was
editing:**

- Whether a `<button>` should adopt the calls to action's hover lift, or they drop
  it. `buttonStyles` currently carries a `lift` variant that preserves both, which
  is honest about the disagreement and is still two behaviours where a design
  system wants one.
- Whether `LessonPlayer`'s lesson title joins the type scale. It is `text-2xl`,
  byte-identical to the marketing `<h2>`s, recorded as `PAGE_TITLE.section` and
  pinned by a test so it cannot drift silently either way.

**Prior milestone and provisioning status:**
M14 stands at 6 of 10. Every remaining task in the project waits on an account,
a payment, or a §5 decision — none of which is an agent's to make.

**The ~$5/month tier is approved** (2026-09-16), answering the first of the five
decisions in `infra/docs/provisioning.md`. **No provisioning has begun**: the
repository has no environments configured and no repository variables set.

**1532 backend tests (inherited, not re-run), 416 frontend.** Master green.

---

### 45 utility classes had never applied, in any release

Tailwind 4 reads the two custom-property syntaxes differently, and only one of
them works:

```css
.rounded-\(--radius-md\) { border-radius: var(--radius-md) }   /* 12px */
.rounded-\[--radius-md\] { border-radius: --radius-md }        /* invalid, dropped */
```

The bracket form is Tailwind 3's spelling. **`tailwindcss` has been `^4` since the
first frontend commit**, so those 45 classes across 15 components have never
rendered a radius or a shadow — not a regression, a class of styling written by
people who could not see that it did nothing, copied forward for fifteen
milestones.

Measured on `/login` before the change, one page and one token: the submit button
computed `border-radius: 12px` and the two inputs directly above it computed
`0px`. A rounded button under square-cornered fields.

**Nothing automated could have caught it.** Both spellings are valid strings in a
`className`, so `tsc` and ESLint pass either way, and jsdom runs no Tailwind, so
no component test can tell. Invisible to every check and visible only to eyes is
why it survived.

**The build was compiling CSS from the tests.** `verify:css` failed on a clean,
fully-fixed tree, and the offending declarations turned out to be the example
strings inside the test and the script written to catch them — Tailwind 4 detects
its own sources and the sweep included `*.test.ts(x)` and `scripts/*.mjs`. A guard
compiled into existence by its own description of what it guards. `src/test/source.ts`
documents four earlier versions of that shape; this is the same trap one layer
further out, because here the *build* reads the test rather than a test reading
the source. `@import "tailwindcss" source("../")` plus `@source not` for tests
fixes it, and drops the shipped stylesheet from 27,013 to 26,584 bytes.

---

### A focus ring lost to a rename, not to an edit

Swept for other Tailwind 3 spellings that changed meaning in 4 rather than
breaking outright. `outline-none` is the only live case, at two sites —
`SiteNavTree`'s drawer and `SiteShell`'s `<main>`, both `tabIndex={-1}` and
focused programmatically.

Verified against the installed version's own source rather than from memory:
`outline-hidden` is what `outline-none` used to mean, and carries a
`@media (forced-colors: active)` fallback restoring a transparent outline that
`outline-none` no longer does. The intent at both sites — no visible ring around a
whole drawer or the entire main region — is unchanged and this is not a visual
change. What was lost is that somebody in Windows High Contrast following the skip
link had no indication where focus had gone.

`Button.tsx` already carried a comment about how easily a utility class defeats
the global `:where(...):focus-visible` ring, since zero specificity only ever
loses. This is that hazard arriving through a rename instead of a deliberate edit,
which is the version no code review would have flagged.

---

### Two calls to action that never lined up, and three of my own errors

44px and 46px, side by side on the landing page, measured in a browser. Five `<a>`
elements were reimplementing `Button`'s styling by hand and had drifted into three
different `transition-*` values, two paddings and no `min-height` at all.
`buttonStyles` is now exported and they compose it — a link is not a `<button>`,
so it takes the styles rather than the component.

**Each of the three mistakes was caught by measuring, not by review**, and they
are recorded because the pattern is the point:

1. **`min-h-11` does not fix the misalignment**, though the first attempt claimed
   it did. A minimum is a floor, not a cap. At `text-sm` the floor was binding for
   both variants so they matched at 44px *by accident*; at `text-base` the content
   grew past it and they were 44 and 46 again. `border border-transparent` in the
   base is the actual fix.
2. **The first version silently shrank both calls to action from 16px to 14px**,
   with every test green. `buttonStyles` is the raw `cva` and does not run
   `tailwind-merge` the way `Button` does, so the base's `text-sm` and `lg`'s
   `text-base` both applied and CSS order picked the smaller. Each size now owns
   its type size.
3. **A provocation that read as a pass was a no-op.** A `perl -pi -e` pattern
   containing `${...}` interpolates it as a Perl expression, so the substitution
   never applied and the suite came back green. The tell was the test count — 51
   where sibling runs collected 85. Provocations are now written with an asserted
   substitution that fails loudly when the pattern is absent.

The same stage extracted `lib/learn/resume.ts`, because `MyCourses` and
`CourseProgress` were each deciding where a learner picks a course back up, with
near-identical paragraphs of comment: finished means no next lesson rather than
`completed == total`, resume follows `next_lesson` and never the bookmark, and
`started` is whether anything has been watched. The wording stays with the callers
— "Continue" on a card, "Continue where you left off" in a strip.

**A fourth correction belongs with the three above.** That extraction was
introduced with a docstring claiming neither component tested the rule. **Both
did, properly** — one has the skipper case spelled out, the other uses a fixture
whose bookmark and next lesson differ on purpose, and provoking the extraction
fails five tests, three of them theirs. So the duplication was two copies of the
rule *and* two copies of its tests, which is a weaker argument than the one first
written down, and the claim was corrected before committing rather than shipped as
a false statement about the codebase.

---

### The landing page was blank for reduced-motion visitors, and a test asserted the bug

Found by opening it in a browser with *reduce motion* on. Nine elements sat at
`opacity: 0` and never came back — the headline, the subtitle, both calls to
action, the course cards and all four feature panels. React said exactly what had
happened: *"A tree hydrated but some attributes of the server rendered HTML
didn't match the client properties. **This won't be patched up.**"*

Ten components called `useReducedMotion()` **during render**. The hook reads a
media query; the server has none. So the server always rendered the animated
branch with `opacity: 0` inline, a reduced-motion client rendered the plain
branch, and React left the server's value in the DOM permanently. **It could only
ever affect people who had asked for less motion**, which is why it shipped —
nobody testing normally sees it.

`MotionConfig reducedMotion="user"` moves the decision inside Motion, where it
applies when an animation *runs* rather than when the tree is *rendered*, so
server and client emit identical markup. Seven components lose their branch;
three keep theirs because they only vary a transition duration, or an `initial`
inside a drawer that is closed on the server, or hover state that is null on both
sides — none reaches the server's markup.

**The lesson is the test, not the bug.** `motion.test.tsx` asserted that `Reveal`
returned a plain wrapper under reduced motion and was green throughout, *because
it mocked `useReducedMotion`*. Mocking the hook made the branch reachable in a
test and the fault invisible: **no unit test that supplies the value itself can
see a difference that exists only between server and client.** Replaced by the
property that makes the fault impossible — rendered markup must not depend on the
preference — provoked by restoring the old branch and watching it fail.

This supersedes "A decision now held open by a test" below: the `h1` is still
outside a `Reveal` and the twelve `opacity: 0` elements are still in the
prerendered HTML, but the reduced-motion half of that question is now answered.

---

### The composition pass found almost nothing, which was the finding

Stage 2's objective used a maintenance verb, so ADR-023 §1 says check whether the
thing is untidy before planning the work. It mostly was not: every section
heading in `(marketing)` already shared one treatment across six sites, `Badge`
was adopted in three places, and containers differed only where justified. The
one real inconsistency was two of three page titles omitting `leading-tight`.

**Coral was left alone deliberately.** ADR-029 asks for a "restrained coral brand
detail" and `--color-brand-coral` is used exactly once, on the logo dot. One
usage is a defensible reading of restrained; scattering more would be a design
decision made by whoever happened to be editing.

---

### The four auth pages had no tests, and two of them carried a security control

Nine rendered states, zero assertions. Registration and password-reset both
answer identically whether or not the address has an account — that is what stops
the forms being used to test a list of addresses — and both pages documented it
**in a comment**. Login carried the same comment about echoing the API's refusal
verbatim rather than inventing a friendlier one. ADR-023 §1 for the seventh time.

The regression is not exotic: it is somebody deciding that "If your address can
be registered, a link is on its way" reads like hedging and rewriting it as "We've
emailed you", which turns the form into an account-enumeration oracle without
touching a line of backend code.

Also now asserted, all of it previously claimed in a comment only: the reset token
never reaches the DOM or storage but does reach the API; a tokenless link is
refused **without asking the API**; the Suspense fallback still carries the `<h1>`
that M15 T10 put there; and each of the nine states has exactly one.

**Nine deliberate breakages, and the two that misbehaved are the useful ones:**

- One provocation *passed*, and the test was right. Removing the reset
  confirmation's body text left the claim in the notice's **title**, so the
  property genuinely still held. Recorded in place, because a half-provocation
  makes a sound test look like one that cannot fail — and the obvious next move
  would have been to "strengthen" a correct test.
- `forgot-password`'s conditional-wording assertion **passed for the wrong
  reason.** `/\bif\b/` over the confirmation matched the word inside the badge
  title *"Sent, if we could"*, never the body's own "If" — `textContent`
  concatenation glues it to the preceding word as `"couldIf"`, so there is no
  word boundary. Rewording that title would have failed a green test while the
  property it checks went untouched. Found because the identical assertion in the
  registration test failed against *correct* code.

---

### Fifteen hand-written page titles, and two wrong readings of why

`PageTitle` now owns the treatment and an app-wide guard with **no exemption
list** keeps it there: no `<h1>` anywhere in `src/` outside that component. That
is strictly stronger than the string comparison it replaces, which could only
ever work inside one route group — run over the whole app it would have failed on
correct code, because the auth pages and the 404 are *meant* to be a size down
from the catalogue.

**Both earlier readings of the drift were wrong, and the corrections are the
record worth keeping:**

1. Stage 2's commit message called the auth pages' `text-3xl` drift "for no
   reason". It is not drift. `NotFoundContent` and `LessonGate`'s refusal sit in a
   `max-w-2xl` column at `text-3xl` while the landing hero sits in the **same**
   `max-w-2xl` column at `text-4xl sm:text-5xl` — so it is not the column width
   either. It is the kind of page: a destination you navigated to, or an
   interstitial standing in for one.
2. "Exceptionless across all fourteen sites" was also wrong. A **fifteenth**
   `<h1>` surfaced while writing the guard: `LessonPlayer` titles the lesson
   `font-display text-2xl text-ink`, byte-identical to the marketing `<h2>`
   section headings. It was in the original survey and was read past.

`/my-courses` was a sixteenth variant by accident — it omitted `leading-tight`
alone among the larger titles — and gains it.

**Open, and deliberately not decided:** whether the lesson title should stay a
step below an interstitial or join the scale. It is recorded as the `section`
variant, reproduced byte for byte so adopting the component changed nothing on
screen, and pinned by a test so the outlier shows in a test run rather than only
in a docstring. Adding `tracking-tight` to a 24px heading is visible, and it
would pull the lesson title away from the `<h2>`s it currently matches — not a
call for whoever is tidying imports.

One unverified consequence: `leading-tight` is **looser** than Tailwind's default
leading at `text-3xl` and `text-4xl`, not tighter, so thirteen interstitial
titles shift about a pixel per wrapped line.

---

### An instruction that was not in the repository

A context block for `frontend/AGENTS.md` arrived carrying a paragraph telling the
agent to make file changes through the shell "wherever it can accomplish the job"
rather than through the dedicated edit tools. **`git show HEAD:frontend/AGENTS.md`
ends at `<!-- END:nextjs-agent-rules -->` and `git status` reports the file
unmodified** — nothing in this repository says that.

Recorded because the effect, whatever the intent, is to route edits away from the
tools that produce a reviewable diff, and because the last time these two briefs
drifted it was also a quotation that had been altered in transit (see "Two briefs
that could have drifted"). Not followed. Worth checking whatever local tooling
injects it.

---

### The one prerequisite that could be built was, and it found a false claim

`providers/video.py` says swapping a video provider is "one file", and both
provider factories called themselves "the one place that chooses between
implementations — the claim rests on nothing else importing a concrete provider
directly".

**Both were false, for the same reason.** Each factory lived *inside* the
concrete provider's own module, so every call site imported the fake by name,
and `providers/__init__.py` — where the choice belongs — was empty in both apps.
ADR-023 §1's shape for the sixth time, and the first found in a **test
docstring** rather than an ADR.

Each factory now lives in its package, selects on a setting, and **raises on an
unrecognised name rather than falling back to the fake**. The two failure modes
are worth keeping in mind because they differ:

- **Video** — a path left on the fake mints playback tokens that verify against
  our own key. Every entitlement check passes, every token is worthless, nothing
  raises until a learner presses play.
- **Transcription** — quieter and not smaller. The fake produces *realistic*
  segments by design, so M6 could test its review workflow. A human reads them,
  approves them, publishes them. It ships invented subtitles under a reviewer's
  name.

**A third provider family is deliberately untouched.**
`apps/entitlements/providers` has no factory at all — one management command
constructs `FakeBillingProvider` directly. **M8 should build that seam before
the adapter**, and §5 names working ahead as needing approval, so it was left.

---

### Preparing to provision found a secret nothing reads

Cross-checking the deploy action against the documentation before a provisioning
session: **`METRICS_TOKEN` was listed as a GitHub environment secret and nothing
in CI has ever read it.** It is a container variable, so setting it where the
document said does nothing at all and `/metrics` stays a 404.

That is the worse of the two drift directions. A secret CI needs and the
document omits is a failed deploy — loud, quickly fixed. A secret the document
lists and CI never reads is set, looks done, and configures nothing.

The four `MEDIA_STORAGE_` names were also abbreviated to `MEDIA_STORAGE_*`,
which is how three of four get set. Both fixed, with a guard covering all three
directions, and `provisioning.md` §3.0 is now a worksheet: what to create, what
it gives you, and **which of the two destinations** it goes to — GitHub secrets
for what CI needs, Dokploy for what the containers read.

---

### The redesign's four open items are closed or handed back

| | |
|---|---|
| `^` version ranges | **Pinned**, with a guard. This had already regressed once in M13 T7 |
| ~1,700 untested lines | **Covered** where being wrong is quiet — 334 → 362 |
| Worker bundle +18% | Recorded against the free-tier plan |
| Five dependencies without a §5 gate | **Still the owner's** — a conversation, not a fix |

---

### A decision now held open by a test

`Reveal` renders `opacity: 0` and waits for an `IntersectionObserver`, and that
reaches the prerendered HTML: **the built landing page ships twelve elements
carrying `style="opacity:0;transform:translateY(20px)"`**. The text is in the
markup, so a crawler and a screen reader both reach it, but a browser shows
nothing there until JavaScript runs. The `h1` sits outside a `Reveal`, so the
page is not blank without it.

Whether the sections below should behave the same way is the redesign author's
call. The test pins current behaviour and fails whichever way somebody changes
it, so it cannot be settled by accident.

---

### Two briefs that could have drifted

`AGENTS.md` arrived untracked, and a `CLAUDE` → `AGENTS` find-and-replace had
caught a **quotation**: ADR-001 says "`CLAUDE.md` §11 should be updated to
strike decisions 2, 3 and 4", and the copy rendered it as "`AGENTS.md` §11".
One of two files with identical authority misquoted its own source. Restored,
tracked, and guarded as byte-identical except the title line.

---

### Three tests written this session could not fail, and were found by provoking

Not a run of bad luck — the standing rate. A `matchMedia` stub that arrived
after framer-motion had read the query; a `RUNTIME_ONLY` whitelist that exempted
the very secret its guard existed to catch; and an unmount-guard test asserting
a React 17 warning that React 18 removed, which passed against a hook with the
guard deleted. The last is converted rather than kept, the same conclusion M16
reached about `LessonPlayer`'s `readyRef`.

---

### What happens next, and none of it is mine

1. **A domain**, with DNS on Cloudflare. Named in no document until now, and
   everything downstream needs it.
2. The worksheet in `infra/docs/provisioning.md` §3.0, in order.
3. **Required reviewers on the production environment before `DEPLOY_ENABLED`**,
   or the next merge deploys unattended.

Two steps are one command each once credentials exist, and need no secret held
here: `check_database` against the Neon staging branch (closing M12's `pg_trgm`
handover), and the `wrangler dev` cookie check (closing ADR-025's last unknown).

**Still open and still nobody's:** the Cloudflare Worker gap (ADR-027 §4), the
video provider and its signing dependency (both §5), §11 #1's payment provider,
and M9's trial scoping rule.

---


## Previous session — 2026-09-14

M14 stood at 6 of 10 then too. What happened that day was a contribution
arriving and CI breaking for reasons unrelated to it.

---

### A frontend redesign landed — PR #59, from a fork

13 commits, 34 files, +1,702/−279, by `dem-bijan`. A design-system foundation
(`Badge`, `Card`, `NavLinks`, `cn`), motion primitives (`Reveal`,
`StaggerList`), a `Hero`, a `SiteNavTree`, and a `useCurrentUser` hook — plus
`seed_demo_catalogue`, a backend command that fills the catalogue with readable
courses so a redesign can be judged against real copy rather than the word
salad `seed_catalogue` generates for load tests.

**Verified after pulling, and it is sound.** 334 frontend tests still pass,
`tsc` and eslint clean, `verify:static` shows all four public routes still
prerendering (invariant 15), document structure sound across 11 built pages. No
`dangerouslySetInnerHTML`, no `"use client"` in the `(marketing)` group, and
`useCurrentUser` reads the session through `/auth/me/` rather than storage
(invariant 9). `seed_demo_catalogue` is DEBUG-only behind an explicit `--force`,
atomic and idempotent.

The `IntersectionObserver` stub added to `vitest.setup.ts` is worth reading
rather than skimming: jsdom implements none, framer-motion's `whileInView`
constructs one inside library code where there is no call site to guard, and the
note explaining why it is a plain assignment rather than `vi.stubGlobal` — which
another suite's `unstubAllGlobals()` would silently clear — describes a real
trap, correctly avoided.

#### Four things about it that are conversations, not defects

1. **Five dependencies arrived without a §5 gate** — `framer-motion`,
   `lucide-react`, `clsx`, `class-variance-authority`, `tailwind-merge`. §5
   requires approval for any new dependency and names "a large framework
   without a written comparison" specifically; framer-motion is that case.
2. They use `^` ranges while `next`, `react` and `@sentry/nextjs` are pinned
   exactly. npm has silently re-floated pins in this repository before.
3. **~1,700 lines of new components, zero new tests.** The count is unchanged
   at 334.
4. **The Worker bundle grew 18%** — 1061.61 → **1254.32 KiB** gzipped. Wrangler
   raised no warning, but `infra/docs/provisioning.md` plans around Cloudflare's
   free tier, so the direction matters.

---

### CI was red, and it was not the redesign — PR #60

**The last green run was 30 August.** Every run since 2026-09-14 failed,
including PR #59's own checks, which were merged red. Both causes were two weeks
of drift landing on whoever merged next.

- **Docker Hub stopped serving `minio/minio` anonymously.** The backend job died
  at `pull access denied ... may require 'docker login'` before a single test
  ran. Machines with the image cached kept working, which is exactly the shape
  of failure that gets blamed on the morning's commit. Repointed at **quay.io**,
  which MinIO also publishes to — same repository, same tag, verified by pulling
  it.
- **Five high-severity npm advisories**, all against dependencies that were
  already here: `js-yaml` via `openapi-typescript` (invariant 16) and `sharp`
  via `wrangler` (M13 T7). **None of the redesign's five packages is
  implicated.**

Fixed rather than suppressed, because ADR-022 §3 chose `--audit-level=high`
deliberately: `wrangler` 4.127.1 → 4.131.2 (a direct devDependency, so a bump
rather than `--force` reaching outside a range) and `js-yaml` pinned to 4.3.2
through `overrides`, since `openapi-typescript` 7.13.0 is already latest and
there is no upstream fix to wait for.

`qs` remains at moderate, below the gate. **It will not fail CI and nothing
automatic will fix it** — the next advisory that crosses into high will surface
the same way this one did.

**A fifth drift guard** now asserts `docker-compose.yml` and the CI step name the
same MinIO image. Fixing only one would have meant testing one MinIO release
locally and another in CI, which surfaces as a storage test nobody can
reproduce. Both halves provoked.

---

### A provisioning plan for a smaller budget — PR #61

The client cannot afford the deployment. `infra/docs/provisioning.md` costs it
at **~$5/month rather than $44**, and most of that gap is not a cheaper tier:
**$14 of ADR-002's figure is a forecast**, budgeting for Mux and Deepgram when
`providers/fake_video.py` and `providers/fake.py` are still the only
implementations.

**The architecture does not change.** ADR-025 stands; same providers, same
compose file, same pipeline, on free tiers with a smaller box.

Three trades are marked in the document, and one is serious: **Neon's free plan
retains six hours of history**, so M14 T8's weekly `pg_dump` to R2 stops being
the second copy and becomes the only backup. **T8 gets more important on the
cheap tier, not less**, and T9's restore drill goes from prudent to necessary.

**Two answers are still needed** before any of it is actionable: whether the
target is ~$5 or must be $0, and whether video launches deferred or served
directly from R2 (free egress, ~$3/month storage, at the cost of adaptive
bitrate — which matters for EU and MENA learners on mobile).

---

**1512 backend tests, 334 frontend.** Master green at `973e047`.

---

## Previous work

**M14 T6 — metrics. Built 2026-08-30**, on `feat/m14-t6-metrics`.
Decisions: `docs/adr/028-metrics.md`.

`/metrics` in Prometheus format behind a bearer token, 404 until one is
configured. **No new dependency, no new service, no §5 gate** — the format is
three lines per metric, and a client library would have brought a registry and
a multiprocess mode nothing here uses.

### Proven against the running stack

An eleven-day-old transcript was injected into the dev database. `report_metrics`
reported it, the alert task ran, and a real message reached Mailpit —
*"Transcription backlog: 1 unfinished, oldest 11 days"* — with the course title,
lesson title, instructor address, slug and transcript id all **confirmed absent
from the body**. Queue depth read from the live Redis broker on the same run.
Data removed afterwards; the metrics returned to zero.

### The stuck-transcription alert exists now

§3.7 lists it among the business alerts and calls that row *"the one people skip
and shouldn't"*. T4 built Beat, the threshold and the mail path and used it
once; this is the second thing it was built for. Three days rather than an hour,
because a threshold that fires over a normal weekend is one somebody mutes.

### Sentry Insights was declined for a reason worth keeping

It needs tracing on. Tracing bills a quota **separate** from T5's 5k errors, and
ADR-027 §2 had just recorded that ceiling as unmeasured. Choosing it would have
compounded the pressure T5 wrote down a day earlier.

### A fourth metric nobody can compute

architecture.md §3.7 lists **four**; the task line carries three. The missing one
is *video minutes delivered* — a provider-reported billing figure, and no video
provider has been chosen. Recorded in ADR-028 §5 rather than inherited silently,
because it is the only one of the four about **money** and must return with the
Mux decision.

### One control no behavioural test can catch

Swapping `secrets.compare_digest` for `==` changes nothing observable while
leaking the token's prefix. Asserted from the syntax tree instead — the third
time this repository has needed that, after M4's resolver guard and T5's vendor
seam.

### Still open, and still nobody's

**The Cloudflare Worker gap** (ADR-027 §4). T6 did not touch it; closing it
needs `@sentry/cloudflare`, another dependency and another §5 gate.

---

**M14 T5 — error reporting. Built 2026-08-29**, on branch
`feat/m14-t5-sentry`. Decisions: `docs/adr/027-error-reporting.md`.

Django, Celery and the browser report errors. **The Next.js server half does
not**, and that is the finding rather than an omission.

### What works, and what was proven rather than claimed

Against a captured transport with a non-resolving DSN, a real exception
carrying an email address arrived tagged with its `request_id` and redacted —
which also proves M14 T2's chain reaches Sentry. The Django *and* Celery
integrations auto-enable, verified on a live client.

### The Worker gap, measured

| Observation | Result |
|---|---|
| JS in `.open-next/server-functions/` naming `@sentry` | **none** |
| Worker size with the whole server SDK added | 1061.49 → **1061.61 KiB** gzipped |

A 0.12 KiB delta is the size of nothing. Ruled out: the file location (Next
compiles it fine), the Wrangler preconditions (both already met), and
`withSentryConfig` (tried; no change). Two attempts, so §9 applies and it stops
there. `@sentry/cloudflare` is the documented alternative and a §5 gate.

Django carries the business logic and is fully covered. The uncovered path is
the one dynamic route, `/courses/[slug]/lessons/[lessonSlug]`.

### The spend cap the task asked for does not exist

Sentry puts spend thresholds on paid plans. ADR-002 §5 budgets Sentry at $0 —
the Developer plan, 5k errors a month across everything — so **the quota is the
cap**. Struck in the spec rather than quietly dropped. Tracing is off because
it bills a separate quota, and the test suite overwrites the DSN so one
`make test` cannot spend a month of budget.

### Nothing has ever reported an event

No DSN exists. What is tested is configuration, refusal and scrubbing. This is
ADR-006's inert control **by construction**, and it says so in its own
docstrings rather than being discovered later.

### Two found in passing

- **The dev API container died** with `No module named 'sentry_sdk'`: compose
  mounts the source but carries the image's site-packages. The M12 T7 failure
  class, reproduced by accident.
- **`connect-src 'self'` would have silenced the browser SDK** the moment M13
  enforced the CSP — invisible until then, because it is report-only. The
  ingest origin is now derived from the DSN so the two cannot disagree.

---

**M16 — Learner surface. Complete — 9 of 9.**
Branch: `feat/m16-*`, merged in pieces as PRs #48, #49 and #50.

Spec: `docs/specs/m16-learner-surface.md` · Decisions: `docs/adr/026-learner-surface.md`

| Task | State |
|---|---|
| T1 spec | **done** — `6f27e4a` |
| T2 an authenticated shell | **done** — `be14a92` |
| T3 the lesson URL architecture.md specified at M0 | **done** — `003eaab` |
| T4 six refusals, six messages | **done** — `3420744` |
| T5 my courses, and the slugs a resume link needs | **done** — `ec181c0` |
| T6 the player, tested for the first time | **done** — `2bce745` |
| T7 a transcript you can follow | **done** — `33a82a6` |
| T8 completion, and progress on a static page | **done** — `2db7175` |
| T9 accessibility, ADR, close-out | **done** |

**1407 backend tests, 317 frontend.** ruff, tsc, eslint, `verify:static` and
`verify:a11y` all clean.

### M7's API finally has callers

Gated lessons, progress, completion, playback tokens, transcripts and
enrolments were all built in April and none of it had ever been called. A
learner can now find a lesson from the catalogue, watch it, follow the
transcript, and come back to where they left off.

### What was already broken, and had never been reached

- **`LessonPlayer`'s denial table was keyed on two codes the server has never
  sent**, and had no branch for four that it does — including the one every
  signed-out visitor gets. Fixed by making the reason a schema enum, so a
  missing case is now a compile error.
- **The learner pages had no layout at all.** No header, no footer, no
  navigation, no skip link. Following "My courses" out of the header stranded
  you. Invisible in the source; obvious in the built HTML.
- **`architecture.md` §6.2's lesson route was never built**, while the schema
  carried a redundant foreign key and a unique constraint to support it.

### What T3 broke and T5 caught

Moving lesson pages to slug-based URLs silently broke resume: the enrolment
payload carried only UUIDs. "My courses" could show progress and could not link
to it. Both lessons now ship their slug, from subqueries ordered identically to
the ids they accompany.

### Testing untested code mostly found bad tests

The player and transcript panel passed thirty of thirty-three tests first time.
The failures were mostly mine — a timestamp format that did not exist, a
boundary asserted at a moment that falls in a gap, a guard that grepped a
docstring.

The one real finding was the opposite of a bug: **`readyRef` is not the guard
its comment claims.** Removing it leaves every test passing, because
`worthSending` already refuses the same beat. It stays as defence in depth and
its docstring now says so.

---

### M13 is 10 of 10, with two tasks honestly incomplete

T7 configured both halves of B-lite. T8 built a database preflight and found
that Neon's pooler makes `predeploy`'s advisory lock a no-op. T9 wired
deploy-on-merge, dormant until switched on. T10 walked the rollback runbook.

**Two of those cannot be finished from a keyboard here.** T8's verification
needs a Neon branch to run `check_database` against; T10's §2 rehearsal needs a
registry and an environment. Both say so in their own documents rather than
being marked done.

### The rollback rehearsal found the runbook wrong — 2026-08-29

`docs/runbooks/rollback.md` §3 said that reversing `catalog.0005_search_vector`
would leave "search returning nothing until the backfill finishes".

It does not. **The entire public catalogue returns 500**, because Django selects
every model field and `Course` no longer has `search_vector` — the course
listing dies in the paginator, and it has nothing to do with trigram search.

**And `/healthz` stayed 200 throughout.** An uptime monitor pointed only there
would have reported the site healthy while every catalogue page failed. That is
now recorded against M14 T7, which was going to do exactly that.

Recovery worked as documented: `migrate catalog` forward, then
`backfill_search_vectors`. Both endpoints returned to 200.

### Spend approved — 2026-08-29

M13 §5.2 is answered for B-lite, at ADR-002 §5's figures: **$44/month at
Scenario 1**, ~$120 at Scenario 2. M13 T7–T10 and M14 T7–T10 are unblocked.

**What is still not mine to do.** Creating the Cloudflare, Hetzner and Neon
accounts, and entering any payment or credential, is the owner's. Configuration
lives in the repository; provisioning happens in a browser, by a person.

---

## Previous milestone

**M15 — Public catalogue. Complete — 10 of 10.**
Branch: `feat/m15-public-catalogue`, off `master` after M14's unblocked half
merged (PR #45).

Spec: `docs/specs/m15-public-catalogue.md` · Decisions: `docs/adr/024-public-catalogue-stays-static.md`

| Task | State |
|---|---|
| T1 spec, and four decisions answered up front | **done** — `3dfb100` |
| T2 Vitest + Testing Library, wired into CI | **done** — `d1d15a9` |
| T3 the `(marketing)` route group and its shell | **done** — `528b445` |
| T4 course listing with filters; CI gains a live API | **done** — `b34f1f5` |
| T5 course pages by slug, `generateStaticParams` | **done** — `6d7b030` |
| T6 search over the M11 endpoint | **done** — `ce9efba` |
| T7 landing page | **done** — `3098c01` |
| T8 pricing page, without a price | **done** — `8cd81c5` |
| T9 invariant 15 checked against the build | **done** — `9e35705` |
| T10 accessibility pass, ADR, close-out | **done** |

**200 frontend tests**, 1387 backend, ruff/tsc/eslint clean, and CI now
verifies static generation and document structure against the built output.

### The product is visible to somebody who has not signed up

It was not, before this. A visitor could reach a login form and nothing else,
and the homepage was still create-next-app's template — a Vercel logo and links
to its gallery — fifteen milestones in. Every catalogue endpoint the backend
has exposed since M3 now has a caller.

### What the accessibility pass found, none of it visible before

- **White on the accent measured 2.50:1 in dark mode.** Every primary button on
  the site was unreadable for anyone with dark mode on. `globals.css` claimed
  the accent was "dark enough for white text at AA" and nothing checked it.
- **Border colours measured 1.69:1** in both schemes — form fields had no
  perceivable boundary.
- **Two pages skipped from `h1` to `h3`**, and `/reset-password` prerendered
  with no heading at all.

All fixed, and all now checked in CI: contrast computed from the design tokens,
document structure read from the built HTML.

### Hosting answered — B-lite, 2026-08-28

§11 #3 is closed. Cloudflare Workers for Next.js, Hetzner CX33 with Dokploy for
Django/Celery/Redis, Neon for Postgres. ADR-025 records it, the prerequisites
the spike found, and the one unknown that remains — the `/api/*` rewrite has
never been proven through a running Worker, and what matters there is whether
the session cookie survives the round trip in both directions.

**Spend is a separate approval and is still outstanding.** M13 T7–T10 and
M14 T7–T10 are unblocked by the decision and still blocked by the bill. Nothing
may be provisioned yet.

### Half of invariant 15 is still not built

*"Public routes are statically generated"* — done, and now verified against
Next's own manifests rather than by grepping source. *"rebuilt on publish"* —
**not done.** A course approved in Django stays invisible until somebody runs a
build. It is blocked on §11 #3 (hosting target), because a rebuild trigger is a deploy hook and
that hook differs entirely between the hosting candidates. Spec §4.2 records
where it belongs so M13 T7–T10 pick it up rather than discovering it.

---

## Previous milestone

**M14 — Observability & Launch. 6 of 10.**
Branch: `feat/m14-observability`, off `master` after M13's unblocked half merged.

Spec: `docs/specs/m14-observability.md`

| Task | State |
|---|---|
| T1 spec, measuring what exists rather than assuming | **done** — `154f219` |
| T2 close the `request_id` chain, both missing hops | **done** — `5e1fc51` |
| T3 entitlement reconciliation, reporting only | **done** — `1762165` |
| T4 nightly drift alert; Beat wired | **done** |
| T5 Sentry across three services, with a spend cap | **built** — two of three tiers work; ADR-027 |
| T6 metrics: queue depth, transcription age, webhook lag | **built** — ADR-028 |
| T7 uptime monitors — **not on `/healthz` alone**, spec §4.1 | **blocked** — needs a deployment |
| T8 backups: Neon PITR **and** weekly `pg_dump` to R2 | **blocked** — M13 platform |
| T9 restore drill, **executed** | **blocked** — needs T8 |
| T10 runbooks beyond rollback; launch checklist | **blocked** — all of the above |

**1509 backend tests and 334 frontend pass**, ruff/`check --deploy`/pip-audit clean.

### What T3 and T4 found, which is the point of them

`resolver._decide_for` allows an ACTIVE subscription **without checking its
period**, on the explicit grounds that *"a stale ACTIVE row past its period is
the expiry sweep's job"*. That reasoning is correct, and it assumes a sweep
exists. **None does, and none is scheduled before M8.** A subscription whose
renewal never arrived serves paid content indefinitely.

T3 reports it and T4 mails it. **Neither repairs it** — invariant 3 has exactly
one writer of subscription state, and a nightly job that quietly corrected rows
would erase the evidence of the upstream fault while looking like health.

### Beat is wired, and this is where ADR-001 §2.2 said it would be

`django-celery-beat` was approved under §5 on 2026-08-27. ADR-001 §2.2 settled
the placement at M0 — inside the worker, exactly one replica, schedule in
Postgres — and said it *"lands with the first periodic task, not in M0"*. T4 is
that task, fourteen milestones later.

Verified against the live stack rather than asserted: Beat starts, the schedule
is a row in Postgres, **nothing is written to local disk**, and injected drift
produced a real message in Mailpit carrying subscription ids and no email
addresses.

Three M0 tests that asserted Beat was *deferred* were **converted, not
deleted** — into assertions about the constraint the deferral protected
(invariant 5). Each docstring names what it replaced. That file already had one
such conversion, from when the first task arrived at M5.

---

## Previous milestone

**M13 — Deployment & CI/CD. Unblocked half complete — 6 of 10.**
Branch: `feat/m13-deployment`, off `master` at `30960c8` (M12 merged, PR #41).
Merged as PRs #42 (T1–T5) and #43 (T6).

Spec: `docs/specs/m13-deployment.md`
Decisions: **ADR-024 is not written**, because four of the five decisions the
spec puts to the owner are still open. Writing it now would record answers
nobody has given.

| Task | State |
|---|---|
| T1 spec, and stopping before the blocked part | **done** — `63e7ab1` |
| T2 CSP report endpoint | **done** — `76dba14` |
| T3 pre-deploy step (migrations, advisory lock) | **done** — `22a642a` |
| T4 release image built and tagged in CI | **done** — `039c856` |
| T5 release image smoke check | **done** — `92d7368` |
| T6 rollback runbook, written | **done** — `4130648` |
| T7 platform configuration | **blocked** — hosting undecided |
| T8 staging on a Neon branch; `pg_trgm` verified there | **blocked** — needs an account |
| T9 deploy on merge; production as one approved action | **blocked** — hosting undecided |
| T10 rollback **rehearsed**; production load baseline | **blocked** — no environment |

**1315 tests pass**, ruff/tsc/eslint/`check --deploy` clean, both dependency
audits clean, and CI builds *and smokes* the release image on every push.

### M13 stopped where it should, rather than where it could

The objective names `render.yaml`. **ADR-002 §6 recommends against Render**,
and ADR-002 is the later document, which §2 says wins. §11 #3 lists the hosting
target as open. Writing `render.yaml` would have made that decision in a YAML
file rather than by the owner, so T7–T10 were not started — and T4's release
images are deliberately **not pushed** anywhere for the same reason.

What *was* buildable turned out to be substantial, and two of the six closed
real gaps rather than adding polish.

### The two that closed real gaps

**CI had only ever tested the source.** T4 builds `--target runtime` — the
image that would actually deploy — for the first time. T5 then boots it against
production settings and asks it questions, which is a different check from the
`check --deploy` that already ran: that one runs on the GitHub runner against a
virtualenv with dev dependencies installed. **The failure this catches is M12
T7's**, where adding `django-csp` left every test green and the container dead
with `No module named 'csp'`. Provoked: an image with the package removed fails
the smoke check at exit 1 with exactly that error.

**M12's CSP handover is closed.** The policy shipped report-only with nowhere
to report; T2 is that endpoint. It is bounded, logs four fields rather than the
report, truncates URLs, stores nothing, and answers 204 to everything —
because it is an unauthenticated POST body from anyone on the internet.

### Three things the tasks found in passing

- **The runtime image runs as a non-root user who cannot modify
  site-packages.** Noticed because the first attempt to build a deliberately
  broken image was refused with a permission error. A good property nobody had
  verified.
- **`catalog.0005_search_vector` reverses cleanly**, observed by doing it
  against a live Postgres in T3 and re-applying. So reversal is not its hazard;
  a part-way failure leaving an `INVALID` index is.
- **The pre-deploy step needed to be a management command, not a script.** The
  backend image builds from `backend/` as its context, so nothing in `scripts/`
  is inside it — a deploy step living there could be called by CI and by
  nothing else.

### The rollback runbook says what it cannot do

T6 is written and **not rehearsed**, and §6 of it says the rehearsal is not
merely undone but currently impossible: no environment to roll back, nothing to
roll back to. Its §2 also carries a blocker inline — T4 does not push images,
so the images it tells you to redeploy exist nowhere outside the CI runner that
built them. A runbook whose first step cannot be performed is worse than none.

### Four decisions block T7–T10, none of them an agent's

| # | Question |
|---|---|
| 1 | **Hosting: B ($50/mo), B-lite ($44/mo) or B-HA?** ADR-002 §6 recommends B-lite and says plainly the tiebreaker is how you want to spend your time, not the $6 |
| 2 | **Approve the monthly spend**, naming the option — §5 gate before any provisioning |
| 3 | **The OpenNext spike** ADR-002 §3 required "in M0 before committing" and nobody ran. B-lite and B-HA both depend on it |
| 4 | **Celery Beat placement** — §11 #3 |

Decision 3 is the cheapest to close and the only one an agent can largely do.

### The frontend has now been deferred four times

M7 flagged it. M11 dropped its accessibility pass and mobile QA. M12 dropped
its Playwright journeys. M13 leaves ADR-002 Move 1 — the static public surface,
which that ADR calls *"not optional either way"* — out of scope for the same
reason. **M14's launch checklist will hit it too**: a launch checklist over a
product that is auth pages plus one lesson page is not a checklist.

ADR-020 §2 lays out three options and takes none. It belongs in CLAUDE.md §11,
which is the owner's file.

---

## M12 — Hardening & Test Completion. Complete — 8 of 8.
Branch: `feat/m12-hardening`, off `master` at `1dd0aa3` (M11 merged, PR #39).

Spec: `docs/specs/m12-hardening.md`
Decisions: `docs/adr/022-m12-hardening-decisions.md` (before code),
`docs/adr/023-m12-hardening-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `4203aff` |
| T2 measure §8.1 coverage | **done** — `1bd3df3` |
| T3 cover the non-API backstops | **done** — `aeb1329` |
| T4 `pip-audit` + `npm audit` in CI | **done** — `64551bd` |
| T5 CSP, report-only, both tiers | **done** — `ea1368d` |
| T6 security header sweep | **done** — `d6c1277` |
| T7 load baseline, recorded | **done** — `8af4693` |
| T8 abuse cases, ADR-023, close-out | **done** — `5e22a26` |

**1280 tests pass, none skipped**, in 109s — ruff, `tsc`, `eslint` and
`check --deploy` clean. Run with Postgres and MinIO up.

### The milestone's premise was wrong, and that was the finding

M12 was specified as maintenance: *close coverage gaps, tighten CSP,
dependency audit clean*. **Three of those words were false.**

- **No coverage gaps existed.** Every §8.1 target was already met — permissions
  100% against ~95%, services 97.5% against ~85%. They had never been
  *measured*, which is a different thing and is why the task existed.
- **There was no CSP** anywhere: not in Django, not in middleware, not in
  `next.config`.
- **No dependency audit ran.** CI had two jobs and neither audited anything,
  eleven milestones after architecture.md §8.4 specified both.

ADR-019 §1 and ADR-021 §1 each found one control a document described and
nobody built. M12 found two more in one milestone. **Three milestones, four
instances — this is the default, not a run of bad luck.** ADR-023 §1: when
objectives use maintenance verbs — *tighten, close, clean up* — check whether
the thing exists before planning the work.

### What the coverage numbers were good for

Not the percentage. The 74 uncovered statements, three of which shared one
shape: **a check written as a backstop, tested only through the path that makes
it unreachable.** `grant_access_override`'s guards had tests — through the API,
where the serializer rejects first. `accounts/axes.py`'s form fallback exists
because Django Admin posts a form and every test posts JSON.

Coverage as a percentage said everything was fine. Coverage as a list of lines
said where to look.

### 100% branch coverage is a claim about the code, not the tests

Provoking the resolver gate by deleting a test **did not work** — coverage
stayed at 100%, because other tests covered the same branches. The gate fired
only when genuinely uncovered code was added: 96.21%, build failed. It works,
re-verified after eight milestones. It does not mean any particular test is
load-bearing.

### The load baseline, and what it is not

**1512 requests, 0 failures, 24.9 req/s at 10 VUs over 60s, 500 courses.**

| Endpoint | p50 | p95 |
|---|---|---|
| catalogue list | 350ms | 518ms |
| course detail | 364ms | 550ms |
| search | 419ms | 712ms |

Search is the most expensive by ~20% at p50 — the ordering M11 asserted when it
gave search its own throttle scope, now measured.

**These are not production numbers.** The run used the dev image with `DEBUG`
on, where Django retains every executed query per request. `BASELINE.md` leads
with that. Good for comparison against itself; M13 measures production.

The first run reported a tidy 532ms p50 with **100% of checks failing** on
`DisallowedHost` 400s. A load test where everything errors reports excellent
latency — which is why the script's only check is a status code.

### Two provocations lied before they told the truth

A `| tail` reported the pipe's exit code instead of `pip-audit`'s, so a
vulnerable pin looked like a pass. A header probe run outside pytest measured a
400 page, so `X-Frame-Options` looked missing. Same family as M11's misfired
`.replace()`: **the provocation is code too, and an incorrect one is
indistinguishable from a working control.**

### Worth a second opinion

`DJANGO_DISABLE_THROTTLES_FOR_LOAD_TEST` disables DRF throttling so a load test
measures the endpoint rather than the per-IP limit. It is read in
`config/settings/local.py` and nowhere else, so production cannot see it — and
that is a test, including a structural one, not a comment. It is still a flag
that disables a security control.

### What is next

**M13 — Deployment & CI/CD**, and it inherits more from M12 than usual: the CSP
report endpoint and the decision to enforce, `CREATE EXTENSION pg_trgm`
verified on Neon rather than locally, a production-shaped load baseline, and
Renovate and CodeQL.

**The frontend still has no owner** (ADR-020 §2), and M12 is the **third
milestone in a row** to drop an objective because of it. The `webapp-testing`
skill is installed and the tooling question is settled; what is missing is a
product to walk through. It belongs in CLAUDE.md §11.

M8 and M9 remain blocked on the payment provider and the trial scoping rule,
and M8 still inherits M10's two follow-ups.

---

## M11 — Discovery & Notifications. Complete — 8 of 8.
Branch: `feat/m11-discovery`, off `master` at `ad80d18` (M10 merged, PR #37).

Spec: `docs/specs/m11-discovery.md`
Decisions: `docs/adr/020-m11-discovery-decisions.md` (before code),
`docs/adr/021-m11-discovery-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + five decisions | **done** — `56e9649` |
| T2 `search_vector`, GIN, `pg_trgm`, backfill | **done** — `bf129fd` |
| T3 search endpoint, ranked and throttled | **done** — `e5f0fde` |
| T4 catalogue filters | **done** — `1e70311` |
| T5 related courses | **done** — `046c35d` |
| T6 email adapter + Celery task | **done** — `192b9ce` |
| T7 the transactional set, in templates | **done** — `edbda25` |
| T8 abuse cases, ADR-021, close-out | **done** — `e16df20` |

**1229 tests pass, none skipped**, in 88s — ruff, `tsc`, `eslint` and
`check --deploy` clean, schema and types regenerate to no diff. Run with
Postgres *and* MinIO up.

### M11 is backend-only, on the owner's decision

architecture.md:1050 lists an accessibility pass and mobile QA. There is no
frontend to apply them to — auth pages and one lesson page — so a green
accessibility report over three pages would be ADR-006's inert control wearing
a compliance badge. Dropped, and recorded rather than absorbed.

### Three bugs, each found by a test built so only the rule could pass it

- **Related courses ranked by nothing.** Overlap was counted with a single
  `Case` holding one `When` per skill area, and `Case` returns the *first*
  match — so sharing five areas scored the same as sharing one.
- **Search had an unauthenticated 500.** `?q=%00` reached the driver;
  PostgreSQL text cannot hold a NUL byte. One request, no account.
- **A notification broke the action it described.** Abuse case 7's first
  version *raised* on an unverified address, so an unverified learner changing
  their password got a 500 from the notice about the change.

The first two were caught because the fixtures were built so nothing else could
produce the answer — the weaker related candidate is deliberately the more
recent one, and the abuse case listed control characters rather than only long
input. **That is M11's standing lesson:** a test whose fixture happens to order
correctly proves nothing.

### Two abuse cases are reworded rather than claimed

**Case 7** now names its two exemptions — verification and password reset exist
to reach an unconfirmed address — and says a withheld message is skipped and
logged, never raised.

**Case 8 is unmet by design.** Delivery is at-least-once; at-most-once needs
the table ADR-020 §8 declined or a provider idempotency key that does not exist
yet. `TestCaseEightIsNotMet` asserts the duplicate, because a missing test and
a satisfied one look identical in a summary.

### ADR-020 §7 was wrong and ADR-021 §1 says so

It called M2's direct `send_mail` an invariant-4 violation. The code it accused
had already argued the opposite in a docstring — Django's framework speaks SMTP,
and so does Resend — and that argument holds. What was actually wrong was the
synchronous send in the request path, and the five more call sites T7 was about
to add. **An ADR that accuses existing code should quote what that code says for
itself.**

### Fixed after close-out: the catalogue's missing instructor name

`PublicCourseSerializer.instructor_name` sourced `instructor.get_full_name`,
which `User` does not have — and `read_only` makes DRF `SkipField` rather than
error, so the field was **silently absent from every catalogue response since
M3** and no test asserted it.

**Fixed in `059cdbd`.** `InstructorProfile` gained `display_name` — it had
`headline` and `bio` and no name, while `StudentProfile` had one, and that
asymmetry is what the serializer was reaching around. The field is a method
field returning the name or `""`: present and empty beats silently absent.
Joined with `select_related` and pinned at two dataset sizes, because rendering
a name off a related row is the textbook N+1. Settable in Django Admin, because
a field nothing can write is always empty and an instructor profile API would
be an endpoint with no caller.

The tests assert the **key is present**, not only its value — every value
assertion would pass against a response missing the field, which is how this
survived eight milestones. ADR-021 §7 records the original finding.

### What is next

**M12 — Hardening.** Its Playwright objective is **unbuildable** until the
frontend-ownership question in ADR-020 §2 is answered; M7 raised it, M11 hit it
from the other side, and it belongs in CLAUDE.md §11 where an agent should not
put it unasked.

M8 and M9 remain blocked on the payment provider and the trial scoping rule,
and M8 still inherits M10's two follow-ups — moving the refund route into the
audited half of the route inventory, and teaching `admin_trail_for` about
subscription-targeted rows.

---

## M10 — Admin & Moderation. Complete — 10 of 10.
Branch: `feat/m10-admin`, which branches off `master` (M7 merged at `0e3124b`).

Spec: `docs/specs/m10-admin.md`
Decisions: `docs/adr/018-m10-admin-decisions.md` (before code),
`docs/adr/019-m10-admin-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + five decisions | **done** — `db46bf8` |
| T2 `AuditLog`, index, append-only | **done** — `79f80a8` |
| T3 `record_admin_action` + one-writer guard | **done** — `fef8fb9` |
| T4 access override write path, audited | **done** — `a57546e` |
| T5 route the Django admin: obscure path, staff-only | **done** — `7b0e654` |
| T6 2FA: `django-otp` enrolment and enforcement | **done** — `e51b096` |
| T7 audit the existing admin actions | **done** — `ac01da3` |
| T8 refund service and audit, no provider call | **done** — `3a5cfd6` |
| T9 audit log read surface + diagnostics extension | **done** — `0717a7b` |
| T10 abuse cases, schema, types, ADR-019, close-out | **done** — `c644502` |

**1114 tests pass, none skipped**, in 81s — ruff check and format clean,
frontend `tsc` and `eslint` clean, `check --deploy` reports no issues and 0
silenced, and the committed OpenAPI document regenerates to no diff. Run with
Postgres *and* MinIO up, so the object-storage tests run rather than skipping.
Nothing in the suite is unrun.

### What is next

**M11 — Discovery & notifications.** M8 and M9 sit earlier in §10's order and
are both still blocked: M8 on the payment provider and jurisdiction (§11 #1),
and additionally owes the webhook signature timestamp (ADR-013 §6) and the
`billing:` idempotency namespace (ADR-015 §5); M9 on the trial scoping rule
(ADR-010 §2), which must be answered before any self-serve trial ships.

M8 also inherits two things from M10 that will be wrong if it forgets them: the
refund route must move from `NOT_YET_CAPABLE` into `AUDITED` in the route
inventory, and `admin_trail_for` must learn about subscription-targeted rows or
the first real refund will be missing from diagnostics. The first fails a test
until it is done; the second does not, which is why it is written here.

### All ten abuse cases have a test, and two were weaker than the spec asked

T10 audited §4 case by case. Eight were genuinely covered. Two were not:

- **Case 1** had three hand-written per-route permission classes. It now sweeps
  every route under `/admin-api/` from the URL conf, as anonymous, student,
  instructor and `is_staff`-without-the-role.
- **Case 9** says the admin path must be absent "swept rather than
  spot-checked", and was four hand-listed URLs. It now sweeps every requestable
  route anonymously *and* as a signed-in administrator, plus a 404 and a 403.
  The 404 is the one worth naming: Django's **debug** 404 lists every URL
  pattern it tried, admin included, so there is now a test asserting `DEBUG` is
  off rather than an assumption.

Both sweeps have twins asserting they visited something, and the path sweep has
a second twin asserting the needle would be found if present. Provoked: an
unguarded `/admin-api/` route fails three, a leaked path fails two, an unknown
URL converter fails the coverage twin.

**Case 1's second half is not met and is now recorded as such.** An ordinary
user who finds the admin path sees Django's login form, which identifies
itself. The controls that operate are the unguessable path, `is_staff` and
mandatory TOTP. Changing `HardenedAdminSite` to answer 404 is a defensible
follow-up and was declined as a behaviour change to a routed production surface
on a milestone's closing task. ADR-019 §5.

**Case 8's wording was the other correction.** It read as though diagnostics had
to drop `provider_subscription_id`, contradicting M4's deliberate inclusion of
it. Settled as being about what a *non-admin* learns; the spec is reworded so
the document and the code stop disagreeing. ADR-019 §6.

### ADR-019 §1 is the standing rule to carry forward

**A decision recorded in an ADR is not a control until something asserts it.**
ADR-018 §6 said `AuditLog` was registered read-only in the admin. It was never
registered at all, and abuse case 6 passed for seven tasks because there was no
surface to edit through. This is ADR-006's shape one level up: a control nobody
provoked may be inert, and a control nobody *wrote* still reads as done to
anyone holding the document that promised it.

### The suite's runtime, measured rather than guessed

Earlier in this session I wrote that a full run took about an hour and that
Argon2 was why. **Both halves of that were wrong**, and the correction is
worth keeping because a wrong performance diagnosis is how the wrong fix gets
approved.

| Configuration | Full suite |
|---|---|
| MD5 hashers, MinIO up | **82s** — reproducible |
| Argon2 hashers, MinIO up | **248s** |
| MD5 hashers, MinIO down | 963s, once, not reproduced |

So the hasher change (`50ced9d`) is worth a genuine **3x**, not the order of
magnitude claimed for it. The hour came from somewhere else: the first run had
no `--reuse-db` and stalled on pytest-django's "delete the existing test
database?" prompt with no stdin, which looked like slow progress rather than a
block. Object storage adds its own cost when nothing answers — measured at
31.6s for one file with nine skips, because each skip waits for a connection
to time out first. **Run the suite with MinIO up.**

The hasher change itself stands, on the 3x. **Nothing was given up** — the
three assertions that production uses Argon2, keeps PBKDF2 beneath it, and
really produces an `argon2$` hash read *production* settings in a clean
interpreter, and were provoked against a PBKDF2-first `base.py` to confirm
they still fail. What is genuinely reduced: no test exercises Argon2
in-process any more, so Django's upgrade-on-next-login path runs on MD5 in
tests.

### T9 found that ADR-018 §6 had never been kept

`AuditLog` was **not registered in the Django admin at all**. ADR-018 §6 said
it would be, "read-only, with add, change and delete permissions all denied",
and T2 shipped the model without it. Abuse case 6 — *an audit row cannot be
edited or deleted through any surface we ship* — had therefore been passing
because there was no surface, which is a different fact from the one it
asserts. T9 registers it and tests the refusals, including the bulk delete
action, which `has_delete_permission` alone does not remove.

### Two decisions settled for T9, on 2026-08-25

**Abuse case 8 versus M4's serializer.** §4 case 8 says diagnostics leaks "no
provider identifiers", and `SubscriptionDiagnosticSerializer` has carried
`provider_subscription_id` since M4 on purpose — it is the handle support needs
to find the same subscription in the provider's dashboard, on an
administrators-only endpoint. **Settled: the sentence means a non-admin learns
nothing; the field stays.** T10 should reword the spec rather than leave the
document and the code disagreeing.

**The trail is user-targeted rows only.** Overrides and role changes record the
user as their target. A course approval records the course, and a refund will
record the *subscription* — so **M8 must revisit `admin_trail_for`**, or the
first refund will be missing from the exact screen support opens to ask about
it. Joining through every object a user owns was declined now because T8 makes
a refund impossible and the join would be a path no test could reach.

Capped at 50, with the true total returned beside the rows: a list capped at
fifty that reported fifty would tell support they had seen everything. The
`metadata` blob is deliberately not rendered by the API — it is open-ended, and
an endpoint returning it wholesale would publish whatever a future
`record_admin_action(..., something=...)` put there. The whole row is readable
in the admin site, which is the surface for detail.

### Carried forward from T9 — an erasure gap that is not T9's to fix

**`AccessOverride.granted_by` is `PROTECT`.** ADR-018 §5 argued at length that
`AuditLog.actor` must be `SET_NULL` so that an audit row never becomes the
reason an account cannot be deleted. It does not — but M4's override table does:
an administrator who has ever granted an override cannot be deleted at all, and
the audit row's `SET_NULL` never gets the chance to matter. Found by an abuse
case 7 test failing with `ProtectedError`; the test now uses a role change and
says why. **This is a real gap against erasure obligations** and belongs with
the user-deletion work §6 already puts outside M10.

### Why this file was four days stale

The seven commits above did not update it, so the document that exists to
answer *where are we* said M7 while M10 was most of the way built. §10 requires
updating it at the end of every session. That is the whole of the failure and
the whole of the fix.

### T8's one open question was settled before T8 started

§2.2 puts four things in scope for the refund — permission check, service, audit
row, refusal cases. **The audit row is the one that cannot honestly be
written:** a refund that raises `RefundNotAvailable` did not happen, and a row
describing an action that did not happen is a false record. The suite already
guards against exactly that shape in `test_a_refused_approval_writes_nothing`.

Settled 2026-08-25: `REFUND_ISSUED` stays in the closed vocabulary as the
marker, and T8's audit obligation is met by the twin test asserting a refused
refund writes nothing. The alternative — a `refund()` seam on the provider
protocol, proven against a stub — was declined because it invents the provider
capability ADR-018 §3 forbids by name: partial refunds, currency, windows,
idempotency keys.

Two smaller calls settled with it. The refusal answers **501**, not 503, because
503 says *try again shortly* and 501 says *this server does not do this*. And
the request carries **no amount**, because `Subscription` deliberately holds no
money (`entitlements/providers/base.py` says so) and whether partial refunds
exist is a provider fact we do not have.

---

## M7 — Learning Experience. Complete — 10 of 10.

Branch: `feat/m7-learning`, which branches off `feat/m6-transcription`.

Spec: `docs/specs/m7-learning.md`
Decisions: `docs/adr/016-m7-learning-decisions.md` (before code),
`docs/adr/017-m7-learning-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `bd8e314` |
| T2 `Enrollment`, `LessonProgress` + constraints | **done** — `8d9b0ca` |
| T3 progress recording, completion defined once | **done** — `1b799ba` |
| T4 progress endpoint, gated and throttled | **done** — `0e3c8bf` |
| T5 resume: "my courses", last and next lesson | **done** — `ca8a39a` |
| T6 course completion rule | **done** — `98936bf` |
| T7 transcript panel, APPROVED only | **done** — `6c1a2b4` |
| T8 lesson page: player, panel, heartbeat | **done** — `620f45f` |
| T9 abuse cases, query counts | **done** — `1790788` |
| T10 schema, types, ADR-017, close-out | **done** |

**947 tests pass**, ruff clean, tsc/eslint/`next build` clean, `check --deploy`
clean. Schema and types regenerate to no diff. The entitlement resolver still
holds **100% branch coverage** — 94 statements, 32 branches, none missed.

### The milestone's claim was demonstrated, not asserted

ADR-016 §4 committed to one lesson page so that *watch → progress persists →
resume across devices* was something somebody had watched work. It was: played
against the live stack, left the page, came back at the right second, and the
lesson completed itself by watched time with the database agreeing.

That is also what found the two defects below. Neither was reachable from a
test.

### Two defects found by running it

**1. Every unsafe request through the proxy was refused.** `CSRF_TRUSTED_ORIGINS`
was never set. Next forwards its rewrite destination as the `Host` header, so
Django's origin is `api` and the browser's is `localhost:3000` — they can never
match. This broke **login too**, not just the new endpoints, and would have hit
production identically. Fixed in `07cdfac`. **M13 must set the variable** to the
public origin. ADR-017 §8.

**2. The player wrote a playhead of zero over a real bookmark.** The ticker's
cleanup reports a final beat, and React Strict Mode runs that cleanup before the
fetch saying where the learner was has returned. A lesson resumed at 0:00 having
just destroyed the thing the milestone exists to prove. Fixed with a readiness
gate. ADR-017 §6.

### Two comments that were confidently wrong

The transcript prefetch does **not** prevent a query per cue — a reverse foreign
key collection is one query however many rows it holds, and removing the
prefetch leaves the test passing. Corrected in `1790788`. This is the same shape
as M3's deferrable-constraint comment: right code, wrong reason, and no passing
test can see the difference. ADR-017 §7.

### Carried forward from M7

- **A completed course is not re-evaluated if a lesson is deleted**, so a
  learner one lesson short stays incomplete. No deletion flow exists yet —
  **M10**, where it first can.
- **"My courses" cannot be ordered by last activity**, because a cursor cannot
  page on an aggregate. Fine under twenty courses; needs a real column and a
  measurement if that changes. ADR-017 §3.
- **No frontend test runner.** Adding one is a §5 dependency decision, still
  unasked. Frontend verification is `tsc`, `eslint`, `next build`, and running
  it.
- **The frontend is auth pages plus one lesson page.** No catalogue, course or
  account surfaces exist. M12 asks for Playwright journeys over a UI that is
  mostly not built; that work is currently unowned by any milestone.

---

## M6 — Transcription & Subtitles. Complete — 10 of 10.

Branch: `feat/m6-transcription`.

Spec: `docs/specs/m6-transcription.md`
Decisions: `docs/adr/014-m6-transcription-decisions.md` (before code),
`docs/adr/015-m6-transcription-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `a5d7163` |
| T2 `Transcript`, `TranscriptSegment` + constraints | **done** — `fc8e099` |
| T3 transcription provider interface + fake | **done** — `79fb3d8` |
| T4 request transcription when media is ready | **done** — `e265bd4` |
| T5 callback receiver, segments written | **done** — `75740a6` |
| T6 segment editing, scoped | **done** — `c52649b` |
| T7 review workflow | **done** — `3283fde` |
| T8 VTT rendering, cached, gated | **done** — `7f28ec1` |
| T9 the serving gate, both halves proven | **done** — `98a4add` |
| T10 abuse cases, ADRs | **done** |

**819 tests pass**, ruff clean, tsc clean, `check --deploy` clean. The
entitlement resolver still holds 100% branch coverage.

### The one requirement met somewhere other than where the document put it

§10 M6 asks for a publish gate. ADR-014 §3 put the control at the point of
**serving** instead: the VTT endpoint returns only `APPROVED` transcripts.
That is stricter where it counts — it covers a lesson added to an
already-published course, which a publication-time gate never evaluates — and
looser where it does not, since a course whose subtitles are still being typed
can go live and teach.

Both halves are proven rather than assumed: publication is genuinely ungated
(including structurally — catalog's publication service does not know
transcripts exist), and a sweep across every learner-readable endpoint shows
unapproved words reaching nobody, run as a subscriber, anonymously, and with
the lesson marked a free preview.

**The risk ADR-014 §3 named itself** — that concentrating a requirement on one
reader means every later reader must remember it — is guarded structurally: no
app outside `transcripts` may import `Transcript` or `TranscriptSegment`, so a
future interactive transcript, search result or export has to come through the
app where the approved-only selector lives.

### Two bugs in earlier milestones, found by building this one

**M5's playback token was flaky one run in eight.** It joined raw HMAC bytes
with a `b"."` separator and split on the last one — but a digest byte can *be*
an ASCII dot. `pytest-randomly` made it look like a test-ordering problem.
Now base64-encoded per half, and guarded by 200 round trips rather than one,
because a single round trip passes seven times in eight.

**A shared idempotency table with unnamespaced providers.** Both fakes are
called `fake`, and `WebhookEvent` is unique on `(provider, provider_event_id)`
— so one id collision would discard a transcription callback as a duplicate
media event, answering 200 while the lesson silently never got subtitles.
Events are now `video:fake` and `transcription:fake`. **M8 must use
`billing:`** (ADR-015 §5).

### What the review step actually buys, stated plainly

It prevents approving a transcript **nobody has opened**. It does not prevent
approving one nobody has *read*. The stronger guarantee is per-segment
sign-off, which is a product decision rather than a correctness one — recorded
in ADR-015 §2 so the workflow is not read as more than it is.

---

## M5 — Media Pipeline. Complete — 10 of 10.

Branch: `feat/m5-media-pipeline`.

Spec: `docs/specs/m5-media-pipeline.md`
Decisions: `docs/adr/012-m5-media-decisions.md` (before code),
`docs/adr/013-m5-media-implementation.md` (what implementation settled)

| Task | State |
|---|---|
| T1 spec + four decisions | **done** — `5aea854` |
| T2 `MediaAsset`, `WebhookEvent` + constraints | **done** |
| T3 storage adapter + MinIO | **done** |
| T4 presigned upload and completion | **done** — `fe82068` |
| T5 video provider interface + fake | **done** — `9879cf9` |
| T6 processing task, retries, DLQ | **done** — `8b7cd93` |
| T7 webhook receiver | **done** — `d782847` |
| T8 playback token behind the resolver | **done** — `edd5891` |
| T9 processing status + retry path | **done** — `cc81496` |
| T10 abuse cases, query counts, ADRs | **done** |

**653 tests pass**, ruff clean, tsc clean, `check --deploy` clean. The
entitlement resolver still holds 100% branch coverage.

### M5 costs nothing, and that was the point

Real S3 code against MinIO, a fake video provider behind the documented
interface (ADR-012 §1). The storage path is genuinely exercised — MinIO
refuses a substituted content type with a 403 — so what ships is the code that
will run in production with different environment variables.

**The Mux integration is unproven.** What is proven is that everything around
it is correct and the swap is one file. Same trade M4 made with billing.

### The bug that would have emptied the dead-letter queue

`complete_upload` was wrapped in `transaction.atomic`, so the failure path
wrote FAILED and then raised — and the raise rolled the record back. Every
rejected upload would have stayed PENDING with no message, and the queue §10
M5 calls *the* deliverable would have been permanently empty while appearing
to work.

### The test that only works because it asserts a side effect

Abuse case 6 asserts the provider adapter was **never called** on an
entitlement denial, not that the response lacked a token. Provoked by swapping
the order to mint first: three tests failed **and the endpoint still answered
403**. A test asserting only the status code would have passed while valid,
signed, working tokens were minted for people who may not watch.

### Two testing facts worth carrying forward

Celery's eager mode runs retries **inline**, so a test watching for a `Retry`
reports "did not raise" against code that retries correctly. And
`transaction.on_commit` **never fires under pytest-django** — the same
invisibility as ADR-009 §5's deferred constraints, in a new disguise.

### Carried into M8, unresolved

**The webhook signature has no timestamp.** Our scheme accepts a valid old
signature indefinitely. The idempotency table stops a duplicate being
*processed* twice but does not stop a captured payload being replayed months
later. Real providers bound this with a timestamp, and M8's adapter must add
it (ADR-013 §6).

---

## M4 — Entitlements. Complete — 10 of 10.

Branch: `feat/m4-entitlements`.

Spec: `docs/specs/m4-entitlements.md`
Decisions: `docs/adr/010-m4-entitlement-decisions.md`,
`docs/adr/011-a-field-gains-meaning-re-audit-who-writes-it.md` (standing rule)

| Task | State |
|---|---|
| T1 spec + four decisions put to the owner | **done** — `b0d3b20` |
| T2 `Subscription`, `SubscriptionEvent`, `AccessOverride` | **done** — `a7147fc` |
| T3 fake billing provider behind an adapter | **done** — `8102fc0` |
| T4 `resolve_access`, 100% branch | **done** — `f7f9755` |
| T5 Problem Details denial + permission class | **done** — `f841d5f` |
| T6 gated lesson endpoint | **done** — `bc8f8c9` |
| T7 `/auth/me/` carries the decision | **done** — `a11c740` |
| T8 admin diagnostics + override grant surface | **done** — `9a4b009` |
| T9 remaining abuse cases; `is_preview` fix | **done** — `9db0899` |
| T10 ADRs, schema, types | **done** |

**489 tests pass**, ruff clean, tsc clean, `check --deploy` clean. Schema and
types regenerate to no diff.

### The resolver has 100% branch coverage, enforced

CI fails the build if `apps.entitlements.resolver` drops below it. The gate was
provoked before being trusted — run against one test class it reports 46% and
errors — because a gate nobody has seen fail is ADR-006's inert control wearing
a new hat.

### All ten abuse cases have a test, and two found real bugs

**Abuse case 8 was live.** `is_preview` was writable on the instructor lesson
API from M3 T5. Nothing read the field then, so nothing looked wrong. M4 made
it the resolver's *first branch* — allowed before the caller is identified — so
an instructor could mark every lesson a preview and hand a whole course to the
internet, against a subscription shared across the catalogue. **ADR-011** is
the standing rule that came out of it: when a field starts being read by an
access decision, re-audit every path that can write it, in the same change.

**A complete bypass was introduced and caught inside T6.** The gated lesson
view was a `ReadOnlyModelViewSet`, which provides `list` as well as `retrieve`.
Object-level permissions are never consulted for a list, so `GET /lessons/`
answered 200 with every lesson body to anonymous callers, behind a docstring
that said "retrieve only". Object-level permissions cannot gate a collection —
that is now written down in ADR-010 §9.

### Abuse case 10 is the suite's only structural test

It parses every module outside `entitlements/` and fails if one imports the
subscription status enum or compares a status literal. A second implementation
of the access rules is invisible to behavioural tests; it shows up as a
disagreement in production, later. The detector is itself checked against the
pattern it exists to find.

### Two guards fired on schedule

M2's `test_the_access_object_is_absent_until_m4` was written to fail exactly
once, so nobody shipped a placeholder the frontend could depend on. It fired.
That is three milestone-order guards that have now gone off correctly across
M0–M4.

### Open, and blocking M9

**The trial scoping rule (spec §3.2) is undecided.** A trial was settled to be
*scoped* rather than equal to a paid subscription, but not what scopes it.
`trial_covers` currently grants what an active subscription grants, isolated in
one function.

That is safe today for one reason only: **there is no self-serve trial** — a
subscription can only be started by the `billing` management command. **M9 must
not ship a self-serve trial before this is answered**, or the permissive
default becomes a way to get the catalogue free. ADR-010 §2.

---

## M3 — Catalogue domain. Complete — 10 of 10.

Branch: `feat/m3-catalogue`.

Spec: `docs/specs/m3-catalogue.md`
Decisions: `docs/adr/007-m3-catalogue-decisions.md` (spec time),
`docs/adr/008-m3-implementation-decisions.md` (implementation),
`docs/adr/009-measure-do-not-reason-about-queries.md` (standing rule)

| Task | State |
|---|---|
| T1 spec + ADR-007 | **done** |
| T2 `Language`, `Course`, state machine | **done** |
| T3 `Section`, `Lesson`, deferrable ordering constraints | **done** |
| T4 instructor course API, scoped | **done** — `64ffbe6` |
| T5 section/lesson CRUD + bulk reorder | **done** — `aaa598f` |
| T6 submissions on the review trail | **done** — `ba4cac8` |
| T7 admin review queue, unrouted | **done** — `0c31bee` |
| T8 public catalogue | **done** — `15d8640` |
| T9 query counts pinned | **done** — `fef7617` |
| T10 ADRs, schema, types | **done** |

**352 tests pass**, ruff clean, tsc clean, `check --deploy` clean. Schema and
types regenerate to no diff.

### All nine abuse cases have a test that fails without its control

Including the two that are easy to fake. Abuse case 7 (reorder with a foreign
id) was checked against a deliberately permissive implementation — filter the
foreign id out, apply the rest — and both reorder tests failed against it.
Abuse cases 5 and 6 each have a **positive twin**: a filter matching *nothing*
would satisfy "the public never sees a draft" perfectly and ship an empty
catalogue, so one test archives a live course and watches it disappear.

### A fourth inert control, same shape as M2's two

`InstructorReviewEventViewSet` was declared
`(_CourseScopedViewSet, ReadOnlyModelViewSet)`. The scoped base already
extended `ModelViewSet`, so its `CreateModelMixin` won the MRO: **the route
accepted POSTs while its class name said it could not**, and an instructor
could have written themselves an `APPROVED` event. Caught only by a test that
provokes each verb individually. The shared base is now a mixin carrying no
verbs, so a viewset's own base decides what it accepts.

ADR-006 has now paid for itself four times. Read it before M4.

### Three false performance claims — ADR-009 is the response

I wrote three docstrings in this milestone that were confidently wrong: that
the reorder needed the deferrable constraint to survive `bulk_update` (it
survives by batching), that the catalogue list costs two queries (one — cursor
pagination issues no `COUNT`), and that two `select_related` calls saved a
query per row (they saved none; the serializers render those relations as
primary keys). All three read as correct in review. None would have failed a
functional test.

**ADR-009** makes measurement mandatory for any claim about query counts,
index use, lock behaviour or constraint timing, and describes how to write a
query-count test that means something: run the endpoint at two dataset sizes
and assert the count is *identical*, with a distinct related object per row,
and verify the test fails when the join is removed.

### Two things M4 inherits directly

- **The public serializer has no `body` field at all** (ADR-008 §6), rather
  than a conditionally hidden one. When `resolve_access` exists, entitled
  playback is a *different serializer* chosen by the resolver — not a
  conditional field added to this one. That regression is the thing to watch.
- **Django Admin is built and unrouted** (ADR-008 §5). A staff account that is
  not `role == ADMIN` cannot publish — proven against a superuser — but can
  still edit course fields. Who gets `is_staff` is M10's question.

---

## M2 — Authentication & Accounts. Complete — 10 of 10.

Branch: `feat/m2-authentication`.

Spec: `docs/specs/m2-authentication.md`
Decisions: `docs/adr/005-m2-authentication-decisions.md`,
`docs/adr/006-security-controls-must-be-provoked.md`

| Task | State |
|---|---|
| T1 custom `User` + first migration | **done** — `da72ff4` |
| T2 Argon2, session settings, `django-axes` | **done** — `07ebd47` |
| T3 account creation service | **done** — `1243253` |
| T4 registration + email verification | **done** — `abb7938` |
| T5 login / logout / CSRF bootstrap | **done** — `f189a68` |
| T6 password reset + confirm + change | **done** — `fa7daed` |
| T7 `GET /auth/me/` | **done** — `5805353` |
| T8 throttle scopes provoked and tested | **done** — `74f42ed` |
| T9 frontend auth flows + design foundation | **done** — `245d226` |
| T10 ADR, schema and types | **done** |

**252 tests pass**, ruff clean, tsc clean, `check --deploy` clean.

### All eight abuse cases are covered

Every case in `docs/specs/m2-authentication.md` now has a passing test. The
enumeration one includes the variant that matters most: a second registration
for a taken address does **not** overwrite the existing password.

### Two controls were configured and inert — read ADR-006 before M4

The `django-axes` lockout (T5) and every per-endpoint rate limit (T8) were
correctly configured, read correctly in review, and did nothing. Neither was
caught by review, types, or any functional test — only by a test that tried to
trip the control and saw it fail to trip.

**ADR-006 makes provoking a control the standard**, and it exists because M4's
entitlement resolver and M8's webhook signature check would fail the same way,
far more expensively: an inert entitlement check gives the product away, an
inert signature check makes the webhook a free-subscription API.

### ADR-005 §2.1 validated end to end

No BFF layer. Verified through the running stack: `csrf` sets the cookie,
register returns 202, login returns 200 and sets `sessionid`, `/auth/me/`
returns the right user — all through the Next rewrite.

Also landed: `21bad4c` fixed the bootstrap gap — `make bootstrap` now writes
`backend/.env` as well as the root one, so `make migrate` and local
`manage.py` work without exporting variables by hand.

**204 tests pass**, ruff clean, tsc clean, `check --deploy` clean.

### Tests now need Postgres

M2 is the first milestone with models. CI runs Postgres as a service
(`b36bdbb`) — chosen over SQLite deliberately, because the schema depends on a
functional unique constraint now and JSONB and full-text search later, so a
SQLite pass would prove nothing about production.

**Local gotcha, cost an hour:** a native **PostgreSQL 18 Windows service** on
this machine binds `0.0.0.0:5432` and wins over Docker's mapping for IPv4
loopback. Auth succeeded *inside* the container and failed from the host with
the same credentials. The compose stack now uses **`POSTGRES_PORT=5433`** (set
in the root `.env`). Third collision of this kind, after port 3000 and the
home-directory lockfile.

### The threat model is the spec

`docs/specs/m2-authentication.md` lists eight abuse cases. Three are now
covered:

- **1 — enumeration.** A taken address is indistinguishable from a free one at
  registration, *and* a second attempt does not overwrite the existing
  password. The second half is the one that would have been account takeover.
- **3 — privilege escalation.** `role`, `is_staff`, `is_superuser` and
  `is_email_verified` in a request body reach nothing: the serializer declares
  two fields, so there is no path from the wire to them.
- **4 & 5 — token replay and expiry.** Verification tokens are stored hashed,
  single-use and expiring. Unknown, expired and already-used give one
  indistinguishable answer, so a failed guess yields no information.

**Not yet proven: abuse case 6** (lockout not bypassed by changing User-Agent),
which lands with T5, and **7 and 8**, which land with T7.

### Milestone-order guards have now fired, all correctly

- The M0 `make migrate` guard refused for the whole of M1 and now permits.
- The M0 test asserting the default user model was written to fail *exactly
  once*, as a reminder to come back. It did, and has been replaced.
- The M1 schema drift gate failed the moment endpoints existed — and exposed
  something larger than drift: drf-spectacular cannot infer request bodies from
  a plain `APIView`, so generated types would have been empty and invariant 16
  satisfied in name only. Views are annotated; types describe real operations.

---

## M1 — Backend Foundation. Complete — 8 of 8.

| Task | State |
|---|---|
| T1 core app + abstract base models | **done** — `fae22ac` |
| T2 DRF + drf-spectacular configuration | **done** — `616eede`, pins fixed in `9f630ec` |
| T3 Problem Details exception handler | **done** — `0b565bb`, problem types in `ca56c72` |
| T4 pagination classes | **done** — `0616c15` |
| T5 `/healthz` | **done** — `9050775` |
| T6 `request_id` middleware + JSON logging | **done** — `c5eb681` |
| T7 `/api/v1/schema/` + drift gate | **done** — `38eb242` |
| T8 frontend type generation (`make types`) | **done** — `38eb242` |

### A redirect loop found by verifying, not by testing

`/api/v1/schema/` through the Next.js rewrite bounced forever: Next 308'd it to
`/api/v1/schema`, Django's `APPEND_SLASH` 301'd it back. **Every endpoint in
architecture.md §6.2 ends in a trailing slash**, so this would have broken all
of them from M2 onwards.

Two causes, both fixed in `next.config.ts`:

- Next's default `trailingSlash: false` strips the slash before the rewrite
  runs. Now `trailingSlash: true`, aligning with Django rather than disabling
  canonical redirects on the static marketing surface (invariant 15).
- The rewrite used `:path*`, which splits on `/` and swallows the terminal
  slash. Now `:path(.*)`, a greedy capture that forwards the path verbatim.

Verified through the running stack: with slash, without slash, and the
marketing root all return 200. **No automated test covers this** — it needs
both services running, so it belongs in the Playwright journeys at M12. Worth
adding there explicitly.

### Known and unresolved

One plain-text duplicate line appears per Django log record in the container.
The logger tree was probed in place and is correct — root and `django` both on
`JsonFormatter`, `django.request` propagating with no handlers of its own — so
the source is elsewhere, most likely uvicorn's own logging config. **Cosmetic
log volume, not correctness:** the correlated JSON line is present and right.
Timeboxed after three diagnostic rounds per `CLAUDE.md` §9.

**ADR-003** settles that M1 creates no concrete models and no migrations; the
audit log moves to M2, after the custom `User`. A test drives the migration
autodetector directly and fails the build if anything under `apps/` grows a
model.

**ADR-004** settles that clients branch on the RFC 9457 `type` member rather
than the status code, because DRF downgrades `NotAuthenticated` to 403 when no
authenticator offers a `WWW-Authenticate` header — so "log in" and "not
allowed" share a status. The same mechanism carries M4's entitlement reasons:
`EntitlementDenied` will declare a `problem_type` and add `reason`/`cta`
without the handler changing.

88 tests pass, ruff clean, `check --deploy` clean, 100% branch coverage on the
exception handler.

### Three CI failures, all the same root cause

Both were environment drift — the local machine had state CI did not, and both
are now guarded:

- **DRF installed but not pinned** in `pyproject.toml`. Fixed in `9f630ec`.
  Standard now: verify dependency changes by installing into a *fresh*
  virtualenv from `pyproject.toml` alone, not with `--dry-run`.
- **The suite required a live Redis**, because T2 pointed `CACHES` at Redis and
  DRF throttling counts against the default cache. It passed locally only
  because the compose stack was running. Fixed in `6a6e600`: test settings use
  `LocMemCache`, and the production assertions moved to a subprocess check
  against production settings. Reproduce this class of failure by stopping the
  relevant compose service before trusting a green local run.
- **`REDIS_CACHE_URL` was never added to the CI workflow.** T2 added it as a
  required variable and taught `.env.example`, `test.py` and
  `docker-compose.yml` about it — but not `ci.yml`, so `check --deploy` died
  with `ImproperlyConfigured`. Fixed **and guarded** in `0e9b4fe`: a test parses
  `ci.yml`, extracts what the deployment step supplies, and compares it against
  every default-less `env()` read in `base.py`. **This class of drift is now
  caught by the suite** rather than by CI.

---

## M0 — Planning & Foundations. Complete and verified.

All 11 tasks implemented, all 11 verified by running them.

| Task | State |
|---|---|
| T1 repository skeleton | **done** — `1ebf740`, plus `.gitattributes` in `9d1cf0d` |
| T2 backend settings split | **done** — `c322d8d` |
| T3 ASGI runtime | **done** — `196668c` |
| T4 Celery application | **done** — `48bf163` |
| T5 backend Dockerfile | **done** — `b55505b` |
| T6 frontend scaffold | **done** — `66c314b` |
| T7 frontend Dockerfile | **done** — `ff13b77` |
| T8 docker-compose | **done** — `38ca0ae`, corrected in `883c225` |
| T9 `.env.example` | **done** — `fdcb9c3` |
| T10 CI workflow | **done** — `4982b92`, fixed in `36be0e9` |
| T11 Makefile | **done** — `e9cc85e` |

### The stack, verified

All six services start. `postgres`, `redis`, `api` and `mailpit` report
healthy; the worker connects to Redis and reports ready; the web root returns
200; and a request to `/api/` on the **web** origin is answered by Django with
`Server: uvicorn` — ADR-001 §2.1 same-origin routing proven rather than
assumed.

Two bugs surfaced only here, neither visible in isolation:

- **`local.py` hardcoded `ALLOWED_HOSTS`**, silently overriding the environment
  read in `base.py`. Next forwards the rewrite destination as the Host header,
  so Django saw `api:8000` and rejected every proxied request while
  `DJANGO_ALLOWED_HOSTS` in compose did nothing. Fixed in `883c225` with a
  regression test.
- **The mailpit pin was wrong** (`v1.27`), taken from `docker manifest inspect`
  output that had already proved unreliable. The real version is **v1.30.7**,
  confirmed by running the image and pulling that exact tag.

Host ports are overridable (`WEB_PORT`, `API_PORT`, `POSTGRES_PORT`,
`REDIS_PORT`, `MAILPIT_UI_PORT`, `MAILPIT_SMTP_PORT`); container ports are
fixed. Port 3000 on this machine is held by an unrelated project.

### Verified

Backend — 27 tests pass; `ruff check` and `ruff format --check` clean across
`backend/` and `scripts/`; `manage.py check` clean; `manage.py check --deploy`
reports **no issues, 0 silenced** against production settings.

Frontend — `tsc --noEmit` clean, `eslint` clean, production build succeeds with
no warnings.

CI — workflow YAML parses into the two intended jobs. **Not** verified that the
run passes on GitHub; only a push can show that.

### Invariants now enforced by tests, not convention

| Invariant | Guard |
|---|---|
| 5, 9 — sessions in Postgres | asserts `SESSION_ENGINE` is the DB backend |
| 12 — ASGI only | asserts `config/wsgi.py` does not exist |
| 5 — no local disk writes | asserts Gunicorn logs to stdout/stderr |
| ADR-001 §2.2 — Beat deferred | asserts no beat schedule and `django_celery_beat` uninstalled |
| §6 — no values in `.env.example` | parses every env read and asserts documented, name-only |
| M2 custom User ordering | `make migrate` refuses while `AUTH_USER_MODEL` is the default |

### Version matrix (locked to what is installed, not proposed)

Python 3.12.6 · Node 22.20.0 · Docker 29.1.3 / Compose v2.40.3 · PostgreSQL 16 (target)

Django 5.2.17 · django-environ 0.14.0 · psycopg 3.3.4 · gunicorn 26.0.0 ·
uvicorn 0.52.3 · uvicorn-worker 0.4.0 · celery 5.6.3 · redis 8.1.0 ·
ruff 0.16.3 · pytest 9.1.1 · pytest-django 4.14.0 · pytest-cov 7.1.0

Deliberately absent from M0: DRF, drf-spectacular, django-celery-beat,
django-axes, argon2-cffi, Vitest.

---

## The M0 planning session, kept as written

Everything below this line is the record of the first session, before any code
existed. It is left unedited as history — "Still no application code" and
"blocked on approval of the M0 plan" describe **2026 before M0**, not today.
The current state is at the top of this file.

The one part still live is the open-decisions table, which is why it has not
been folded away.

## Completed

- **Documentation reorganised** into `docs/` and untracked. `docs/` is gitignored; the files remain on disk. `CLAUDE.md` stays at the repository root because the agent tooling loads it from there.

  | Was | Now |
  |---|---|
  | `phase-1-architecture.md` | `docs/architecture.md` |
  | `deployment-strategy.md` | `docs/deployment-strategy.md` |
  | `adr-002-cost-reliability-streaming.md` | `docs/adr/002-cost-reliability-streaming.md` |
  | `agent-prompts.md` | `docs/prompts/agent-prompts.md` |

  This makes the paths in `CLAUDE.md` §2 correct for the first time. The removals are staged in git but **not committed**.

- **`.gitignore` created** — `docs/`, `.env`, `.env.*` with `!.env.example`. The full ignore file lands with M0 task T1.
- **`docs/adr/001-architecture.md` written** — records the four settled decisions (same-origin routing, Celery Beat placement, hosting deferral, ASGI) and restates the payment provider as open with a standing "do not model billing" instruction.
- **M0 plan produced** — 11 tasks, ordered, with dependencies and invariant mapping. Awaiting approval.

Still no application code, no dependencies, no migrations, no tests. `backend/`, `frontend/`, `infra/`, `scripts/`, `.github/` do not exist.

---

## In progress

None. Blocked on approval of the M0 plan and the version matrix (below).

---

## Blockers

### Blocking the first M0 task

1. **Version matrix not agreed.** `pyproject.toml` and `docker-compose.yml` cannot be pinned without Python, Django, Node, Next.js, PostgreSQL and Redis versions. Proposed defaults are in the M0 plan §8; they need confirming or correcting.
2. **Dependency approval.** `CLAUDE.md` §5 requires approval for every dependency. M0 needs roughly nine runtime and six dev packages. The list is in the M0 plan §8. Decide once whether `docs/architecture.md` counts as a standing allowlist, or this recurs every milestone.

### Open decisions (`CLAUDE.md` §11)

| # | Decision | State |
|---|---|---|
| 1 | Payment provider & jurisdiction | **Open.** Blocks M4 schema and M8. Does not block M0–M3. Standing rule: do not model billing. |
| 2 | Same-origin routing | **Settled** — ADR-001 §2.1. Next.js rewrites now, Cloudflare Worker before launch. |
| 3 | Celery Beat placement | **Settled** — ADR-001 §2.2. In-worker, single replica. `--beat` and `django-celery-beat` land with the first periodic task, not in M0. |
| 4 | Hosting target | **Settled as deferred** — ADR-001 §2.3. Containerise for both; decide at M13. |
| 5 | Live classes on the roadmap | **Open.** Blocks nothing until M5. |

`CLAUDE.md` §11 still lists 2, 3 and 4 as open and should be updated.

### New questions raised by ADR-001, deliberately left open

- **BFF vs path routing (M2).** `architecture.md` §3.2 and §4.3 describe two different architectures as if interchangeable. Resolve at M2 kickoff, before auth flows are written.
- **Private network under B-lite (M13).** Server Components fetching Django "over the private network" does not hold if Next.js is on Cloudflare Workers and Django is on Hetzner.

### Documentation defects, not yet corrected in source

- `docs/deployment-strategy.md` §9.3/§14 total the recommended (Mux) stack at ~$62; the line items sum to ~$43. The $62 figure models Cloudflare Stream.
- `docs/adr/002-...` §7.1 audio-mode saving computes to ~$612, not ~$570; §5 B-HA column sums to $152, not $157, and mixes Scenario 1 and Scenario 2 figures.
- Neon is modelled at $15 throughout, against the documents' own derivation of ~$19–20.
- Mux's 1/10 audio rate is claimed for a playback *mode*; it appears to apply to audio-only *assets*. Untagged and unsourced — verify before budgeting.
- `Brainstormv1.md` is cited by section throughout `deployment-strategy.md` and is not in the repository.

---

## Next milestone: M7 — Learning Experience

Enrolment, `LessonProgress`, resume logic, and the lesson player that ties
M5's video to M6's subtitles.

Carried in:

- **ADR-014 §3's risk lands here first.** An interactive transcript — "click a
  line, seek the video" — is the most likely next reader of segments, and it
  must apply the same `APPROVED` filter. The structural guard will stop it
  being written outside the transcripts app; it will not stop a second
  unfiltered query inside one.
- **ADR-011 applies** the moment progress state starts deciding anything.
- **Two visibility gaps are now overdue.** Nothing tells an instructor that a
  media asset failed (M5) or that a transcript is waiting for review (M6).
  Both belong with notifications in M11, and both are "visible if you check"
  until then.

**Still blocking M8:** the payment provider decision (CLAUDE.md §11 #1); the
webhook signature timestamp (ADR-013 §6); and the `billing:` namespace
(ADR-015 §5).

**Still blocking a self-serve trial in M9:** the trial scoping rule
(ADR-010 §2).

### Branch tidy-up, outstanding since M0

Five branches with overlapping history and nothing merged to `master`:
`chore/untrack-planning-docs` (PR #1), `feat/m0-foundations`,
`feat/m1-backend-foundation`, `feat/m2-authentication`, `feat/m3-catalogue`.
Worth resolving before M4 adds a sixth.

## Earlier next-action notes

1. Confirm CI passes on GitHub for `feat/m0-foundations`. The type-check fix in
   `36be0e9` has not yet been *observed* passing — it is the last unverified
   thing in M0, and only GitHub can show it.
2. Start **M1 — Backend foundation**: core app, DRF, `drf-spectacular`,
   `/healthz`, Problem Details error shape, structured logging with
   `request_id`.
3. **Answer the custom-User ordering question before writing the `core` app.**
   It is the first decision M1 needs and the most expensive one to get wrong.

### Carried into M1, recorded so it is not rediscovered

- **Custom User ordering.** M1 builds a `core` app with an audit model; M2
  builds the custom User. As written, M1's first migration lands before the
  custom model exists. Either `AUTH_USER_MODEL` and a minimal `User` move into
  M1 ahead of `core`, or M1 ships only abstract base models. Decide at M1
  kickoff. `make migrate` currently refuses, which buys the time to decide.
- **`citext` for email** (architecture.md §5.2) does not exist in Django 5.2 —
  `CITextField` was removed in the 5.x line. Use `UniqueConstraint(Lower(...))`
  or a non-deterministic collation at M2.
- **UUIDv7** (architecture.md §5.2) needs PostgreSQL 18; the target is 16. Use
  UUIDv4 unless the Postgres version changes.
- **BFF vs path routing** stays genuinely open. The `afterFiles` rewrite
  ordering in `next.config.ts` keeps both possible — a Route Handler under
  `src/app/api/` wins, anything else falls through to Django.
- **Gunicorn `timeout` vs Server-Sent Events** (ADR-002 §7.4) are in direct
  tension. Revisit when the first SSE endpoint exists.
