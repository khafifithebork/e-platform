# STATUS

**Last updated:** 2026-10-17
**Updated by:** Codex (approved query-consistent catalogue search)

## Latest verification — 2026-10-17: public-page reflow and enlarged text

Homepage, catalogue, published course detail and pricing passed 16 Chrome
scenarios: 320px reflow, 720px zoom-equivalent layout and simulated doubled
font/line sizes at 1440px light and 390px dark-system preference. Public surfaces
retain their fixed-light theme. The final pass waited for header hydration before
text enlargement. All 180 keyboard stops stayed visible; no overflow, tested
heading/control clipping or runtime errors occurred. Desktop/mobile captures were
reviewed together and confirmed. Evidence: `public-reflow-review.json` and
`public-reflow-*.jpg` in the task visualization directory. No product code changed.
Actual browser/native text-only zoom, screen readers and other browsers remain
unverified. This log/runbook update and the drawer-focus regression are uncommitted.

## Latest verification — 2026-10-17: drawer focus during session loss

Search correction is committed locally as `49daff6`. Synthetic 390px Chrome
confirmed that focus stays inside an open drawer when session loss replaces its
account links; Tab still wraps to Close. No product correction was needed.
The matching regression, all 15 SiteNavTree tests, lint and type checking pass. Browser evidence:
`drawer-session-focus-before-review.json` / `drawer-session-focus-before.jpg`
in the task visualization directory. Only this log and the test changed.

## Latest session — 2026-10-17: search results follow the current query

The owner approved the six-file correction on `codex/account-polish`.
Changing a trimmed search query now cancels its active request immediately,
clears the previous error/cards/count and keeps ranked-search mode while waiting
for the unchanged 400ms debounce. Both success and failure handlers ignore
cancelled requests even if their body settles late. Effect cleanup cancels the
timer/request on query changes or unmount. Whitespace-only edits preserve the
current request/results. Clear search still focuses the input and restores the
existing filtered browse list; refused searches still restore browsing and show
the existing inline message. No automatic retry, motion, dependency, API type,
server ranking/throttle or public-route rendering change was introduced.

Six added regressions failed against the original implementation before the fix.
All **751 tests across 59 files** now pass, including 56 focused search/catalogue
tests. Eight added cases cover immediate edit/clear cancellation, late successes,
failures and post-unmount completion, old-error removal, whitespace preservation
and immediate outdated-card removal. Existing debounce, out-of-order, filtering,
failure recovery, clear-focus and escaped-content assertions remain intact.

Frontend lint, type checking, production build and all four artifact gates pass.
Five public routes stay static, 13 built pages pass structure checks, CSS token
references resolve, and largest first load is 322.8 KB against 350 KB. The local
production-settings Django deployment check reports zero issues. Patch whitespace
is clean and the Impeccable detector returned no findings. Ruff is unavailable;
no Python changed. Existing metadataBase, Vite and jsdom scrollTo notices remain.

Nine synthetic Chrome scenarios pass at 320/390/1440px, including dark-system
preference with the deliberately fixed-light public theme and reduced motion.
Mutation observation found no Spanish card appearing after the input became
French. Late success/failure, previously completed results, clear search, 429,
empty results, network errors and whitespace were exercised. Input focus stayed
in place; no overflow, runtime errors or axe WCAG A/AA violations were found.
Before/after, pending/ready, desktop/mobile and refusal captures were inspected
together with no material visual correction needed. Evidence is in the task
visualization directory: `search-race-before-review.json`,
`search-race-before-mobile.jpg`, `search-after-review.json`, `search-after-*.jpg`.
API responses were intercepted synthetic fixtures, not evidence of real backend
ranking or throttle enforcement. Safari/Firefox, physical devices and screen
readers remain unverified. Design guidance now records the corrected behavior.
This batch is uncommitted; no push, merge, deployment or production changes occurred.

## Latest inspection — 2026-10-17: catalogue query/result mismatch

Transcript following is committed locally as `8a8d8ab`; the working tree was
clean before this inspection log. Synthetic Chrome search reproduced a race:
after Spanish began loading, changing the input to French and releasing the
Spanish response during the next 400ms debounce displayed a Spanish card while
the box said French. French results eventually replaced it. Evidence:
`search-race-before-review.json` and `search-race-before-mobile.jpg` in the task
visualization directory. The current request is aborted only when the next
debounce fires. A six-file search-feedback correction is proposed; no product
code has changed pending §7 approval. No push, merge or deployment occurred.

## Latest session — 2026-10-17: transcript following stays inside its panel

The owner approved the four-file correction on `codex/account-polish`.
`TranscriptPanel` now adjusts only its own list's scroll offset by the minimum
needed on a cue change. Visible cues stay still; wholly offscreen oversized cues
align at the top, while partially visible oversized cues remain where the learner
put them. Following is immediate for all motion preferences (0ms, no easing).
No timer, animation, preference branch, dependency or API change was introduced.
Seeking, cue language, `aria-current`, existing styles and server-owned progress
remain intact. Design guidance now records the corrected behavior.

Eight follow assertions reproduced the old ancestor-scrolling implementation.
Geometry fixtures now test the actual required list offset, stillness, gaps,
same-cue updates and both motion preferences instead of requiring the old API.
All existing seeking/language/text-safety assertions remain. Browser inspection
also reproduced a focused cue being clipped during playback. Its additional
regression failed before the safeguard: following now pauses while the list
contains focus and resumes on the next cue change after focus leaves.

All **743 frontend tests across 59 files** pass on the final implementation,
including 64 focused transcript/player tests. Frontend lint, type checking,
production build and all four artifact gates pass: five public routes remain
static, 13 built pages pass structure checks, CSS token references resolve and
largest first load is 322.8 KB against 350 KB. The local production-settings
Django deployment check reports zero issues. Patch whitespace is clean and the
Impeccable detector returned no findings. Ruff is unavailable; no Python changed.
Existing metadataBase, Vite and jsdom scrollTo notices remain.

Final synthetic Chrome playback at 390px keeps document y=0 instead of the
reproduced y=460 while the list follows cues; 1440px remains at y=0 too. The
focused-cue probe keeps the cue visible/list offset unchanged through cue nine,
then follows cue ten after focus leaves, with document position still zero.
Thirteen lesson-state scenarios pass across desktop/mobile, light/dark, both
motion preferences, empty/error/retry, completed/pending and 320px long text.
No overflow/runtime errors were found, focus remains visible and speed targets
measure 44px. Before/after, desktop/mobile/dark/long captures were reviewed
together; the observed focus issue was corrected once and confirmed.

Evidence in the task visualization directory: `transcript-scroll-review.json`,
`transcript-follow-after-review.json`, `transcript-focus-final-review.json`,
`transcript-final-review.json` and their JPG captures. Real provider/video playback,
Safari/Firefox, physical devices and screen readers remain unverified. This batch
is uncommitted; no push, merge, deployment or production configuration changed.

## Latest inspection — 2026-10-17: transcript following moves the mobile page

Reflow notes are committed as `192b04d`. During synthetic playback at 390px,
`TranscriptPanel`'s cue `scrollIntoView` moved the page from y=0 to y=460 while
the transcript list moved from 0 to 24px. At 1440px the page stayed at zero while
the list moved 40px. Reduced motion was enabled, so this is not a smooth-scroll
timing artifact. Captures and `transcript-scroll-review.json` are in the task
visualization directory. Current tests assert the scrolling API call and miss
ancestor scrolling. A bounded panel-only follow correction is proposed; product
code is unchanged pending the owner's §7 approval.

## Latest verification — 2026-10-17: reflow and enlarged-text stress pass

Chrome 155.0.8059.80 passed 32 synthetic scenarios across five authentication
routes, Account, My courses and the lesson. Modes: 320px reflow, 720px layout
(the CSS viewport equivalent of 1440px at 200% zoom), and synthetic doubled
font/line sizes at 1440px light and 390px dark. Long refusals, lesson titles and
transcript cues, plus course empty/error states, were exercised. Across 342
keyboard stops: zero overflow, clipped tested controls/headings/alerts, hidden
focus targets or runtime errors after native scrolling painted. Initial premature
focus samples are retained separately. Screenshots were inspected together.
`reflow-review.json`, `reflow-initial-review.json` and `reflow-*.jpg` are in the
task visualization directory. Actual browser zoom, native text-only zoom, other
browsers and screen readers remain unverified; this does not close all WCAG checks.
No product code changed; only this log and the accessibility runbook were updated.

## Latest verification — 2026-10-17: dynamic lesson first-load assets

Session feedback is committed locally as `6c5099e` and `d105061`; working tree
was clean before this documentation update. Cold isolated Chrome contexts at
390px and 1440px measured the production dynamic lesson with synthetic API data.
Initial HTML references total **323,632 bytes gzip** of scripts/CSS at both widths,
using the existing gate's gzip-level-9 method. At controls/transcript readiness,
rendered scripts/CSS total **338,917 / 341,567 bytes**, respectively, below 350,000.
The ready-state total varies with hydration/prefetch timing; it is not a stable CI
assertion. HTML, API responses, fonts, media and later interactions are excluded.
No runtime errors occurred. Raw asset lists are in `lesson-first-load-review.json`
in the task visualization directory. No real video/provider delivery was measured;
the static bundle gate still does not enforce the dynamic route. Roadmap D5 now
points to ADR-038 and the implemented commits. No product code changed here.

## Latest session — 2026-10-17: inline session-ended notice and navigation recovery

The separately approved UI batch is implemented locally on `codex/account-polish`.
`SessionExpiryNotice` mounts inside the shared main landmark and uses the existing
themed Notice plus a 44px Sign in link. The heading is "Sign in to continue";
the server detail is rendered verbatim as plain text. The action stacks on narrow
screens, long unbroken messages wrap, and server HTML remains neutral. No focus
transfer, animation, redirect, timer, retry or polling is introduced.

Header and rail/drawer now share the identity hook. Confirmed session loss removes
their signed-in links and invalidates pending identity results. Fresh confirmation
resolves identity again, showing a neutral placeholder while waiting rather than
revealing the previous account. Existing pending sign-out and full-page navigation
are preserved. Already-loaded page content and form values remain in place;
existing page refusals and Django access enforcement are unchanged.

The new identity/notice regressions failed before implementation. All **739 tests
across 59 files** now pass, including eight added cases for notice silence, exact
wording/text escaping, focus preservation, neutral SSR, identity invalidation,
recovery to a different account, late responses and pending logout. Existing
assertions were retained. Session reset was added to navigation and identity test
fixtures to isolate simulated browser visits. The actual existing hook test file
was extended instead of retaining a second test file. To keep this UI batch at ten
files, ADR-038 records its presentation guidance; design-system.md was not changed.

Frontend lint, type checking, production build, patch whitespace and all four
artifact gates pass. Five public routes remain static, 13 pages pass the structure
gate, all CSS token references resolve, and the largest first load is **322.8 KB**
against 350 KB. Local production-settings Django deployment check reports zero
issues. Ruff remains unavailable; no Python files changed. Existing metadataBase,
Vite and jsdom scrollTo notices remain.

Eight synthetic Chrome scenarios pass at 320–1440px in light/dark, with reduced
motion, anonymous visits, permission/network failures and long server text. The
notice appears only for confirmed loss, header/drawer identity updates together,
the keyboard focus target is retained and recovery targets measure at least 44px.
No overflow, runtime errors or browser-storage entries were found. The final axe
WCAG A/AA scan found no violations in those eight scenarios. A separate 18-case
header/navigation/logout regression also passes, including full JavaScript-context
teardown on both successful and failed logout. Impeccable detector returned no
findings. Desktop/mobile/light/dark/long-message captures were inspected together;
no material visual correction was needed, then the bounded confirmation completed.

Before/after captures, `session-notice-before-review.json`,
`session-notice-after-review.json` and `session-notice-regression-review.json`
are in the task visualization directory. Real-account expiry, Safari/Firefox,
physical devices and screen-reader announcements remain human verification items.
Detection still waits for an existing observed API request; native downloads and
unload beacons do not detect expiry. No dependency, service, API contract, auth
strategy, access rule or production configuration changed. The observation
foundation is committed locally as `6c5099e`; the approved UI batch is committed
with this status snapshot. No push, merge or deployment occurred.

## Latest session — 2026-10-17: session-loss detection foundation

Header/account navigation is committed locally as `9f08829`. The owner chose an
inline sign-in notice and approved the first six-file detection batch. It is
implemented on `codex/account-polish`: a browser-only presentation store and
tests, API integration and tests, ADR-038 and this status update. No notice or
header/navigation synchronization is wired yet; those remain the next batch.

Successful parsed `/auth/me/` establishes a confirmed observation. Only a request
begun in that state can report session loss for a specific not-authenticated
problem or entitlement `LOGIN_REQUIRED`. Original errors still reach callers,
and the server detail is retained verbatim. Anonymous visits, permission/CSRF,
subscription, network and server errors do not produce an ended observation.
Requests carry ordering and epoch information so stale successes/refusals cannot
overwrite newer observations. Login/logout resets and temporarily suppresses
observation, including late responses from requests begun during those operations.
Fresh `/me` confirmation establishes recovery. There are no timers, polling,
identity/credential retention, browser-storage writes or server-side user state.
Django remains authoritative for authentication and access.

The store was tested before API wiring. A late-response regression reproduced
an in-flight login/logout race and passed after eligibility was captured at
request start. Four request-boundary regressions failed before integration and
then passed. All 731 frontend tests, lint, type checking/production build and
four artifact gates pass. Five public routes remain static; largest first load
is 322.2 KB against 350 KB. Local production-settings Django deployment check and
patch whitespace check pass. The server-isolation assertion was additionally
strengthened to check neutrality after the simulated server environment ends.
Ruff remains unavailable locally; no Python files changed. Existing metadataBase,
Vite and jsdom scrollTo notices remain.

Eighteen Chrome regression cases pass using synthetic intercepted sessions:
320–1440px, light/dark, anonymous/signed-in, account navigation and pending,
successful and failed logout. No overflow, runtime errors or storage entries
were found; full-page logout still clears the synthetic JavaScript-context probe.
Captures and `session-foundation-after-review.json` are in the visualization
directory. They verify unchanged existing UI flows, not a notice that is not yet
implemented. Real-account/session expiry, Safari/Firefox, physical devices and
screen readers remain unverified.

Detection waits for an existing API request; native downloads and unload beacons
are not observation sources. No dependency, API contract, auth strategy, access
rule or production configuration changed. This foundation is local and
uncommitted; no push, merge or deployment occurred.

## Latest session — 2026-10-16: responsive header identity and Account link

The account and mobile-navigation batches are committed locally as `2784f7c`
and `39da43f`. The owner approved the next six-file batch on `codex/account-polish`.
The signed-in header now wraps within its available width, bounds its visible
email to 12rem above `sm`, and retains the full email text/title for accessibility.
My courses and sign-out labels stay on one line; sign-in/sign-out reuse shared
secondary styling with measured 44px targets. Signed-in rail/drawer navigation
now includes the existing Account destination and active-route semantics.
Anonymous and unresolved sessions do not gain that link. Authentication,
session resolution, full-navigation sign-out and browser-storage behavior are
unchanged; no new motion, dependency, asset, token or API is introduced.

The missing Account-link regression failed before implementation. All 711 frontend
tests pass, including new long-email accessibility, account-link positive/negative
cases and delayed sign-out checks. The first production build caught unsupported
Testing Library `exact` options accidentally copied from the browser API; removing
those invalid options preserves string-name matching and all 32 focused tests
and type checking pass. Final lint, production build/TypeScript and all four
artifact gates pass. Five public routes remain static; the largest first load
is 321.8 KB against 350 KB. The design detector and patch whitespace checks pass.
Docker was off, so the first deployment check could not run; the existing local
stack was restarted and the production-settings Django check reports no issues.
No local volume or production data was changed. Ruff remains unavailable locally,
with no Python changes. Existing metadataBase/Vite/jsdom notices remain.

Eighteen Chrome cases pass across 320, 390, 640, 768, 1024 and 1440px, light/dark
themes, anonymous and signed-in states, long email, and pending/success/failure
sign-out. Reduced motion was enabled for these cases. No overflow, runtime page
errors or browser storage entries were found. The full email text/title survives
visual truncation, Account opens through the drawer with active-route feedback,
and sign-out retains a full navigation that clears the synthetic JS-context probe
on both success and failure. Screenshots required no visual correction.

Before views (`header-before-*`), after captures and `header-after-review.json`
are in the visualization directory. Session/logout responses are synthetic and
intercepted; no real account session was changed. Real-account behavior,
Safari/Firefox, physical-device and screen reader checks remain unverified.
The owner authorized committing this verified batch locally. No push, merge or
deployment is authorized here.

## Latest session — 2026-10-16: mobile navigation without content overlap

The owner approved the six-file navigation batch on top of the pending account
changes on `codex/account-polish`. Below `xl`, Site map now occupies an in-flow
row above learner content instead of floating over fields and transcripts. Its
shared secondary styling has a measured 44px height. Users scroll to the top to
reach it; the desktop rail and public editorial navigation remain unchanged.
The footer no longer reserves extra space for a floating control. Existing root
scroll padding and its focus-safety tests are retained.

A new regression first reproduced the old exit animation leaving the dialog
visible after focus and scroll lock had been restored. Drawer/backdrop mounting
and removal are now immediate under both motion preferences. The render-time
reduced-motion hook is removed. Existing focus containment/restoration, Escape,
backdrop, route-change and desktop-resize cleanup behavior is preserved and
covered, including new immediate close, route-change and backdrop tests. New
shell tests cover navigation/content order and editorial isolation.

All 707 frontend tests pass. Lint, TypeScript/production build and the four
artifact gates pass; five public routes remain static, document structure and
CSS tokens are sound, and the largest first load is 321.8 KB against 350 KB.
The design detector found no issues, the patch whitespace check passes and the
local production-settings Django deployment check reports no issues. Ruff remains
unavailable locally; no Python files changed. Existing metadataBase/Vite and
jsdom scrollTo notices remain.

Thirteen final Chrome cases cover 320px/390px/tablet navigation in light/dark and
both motion preferences, account and lesson views, desktop rail and public shell.
Keyboard focus trapping/restoration, immediate Escape/backdrop close, route-change
closing and resize scroll release pass. No account field overlap, horizontal
overflow or runtime errors were found. Screenshot review confirmed the floating
control is gone; final captures frame the viewport correctly for the drawer and
reset the lesson capture to the top after existing transcript auto-follow.
Before views are retained in the prior account/lesson captures; final screenshots
and `navigation-after-review.json` are in the visualization directory.

Learner responses are synthetic and intercepted; no account or progress was
changed. Safari/Firefox, physical-device and screen reader checks remain
outstanding. No dependency, asset, API, access rule, palette or production
configuration changed. The owner authorized committing the verified account and
navigation batches locally. No push, merge or deployment is authorized here.

## Latest session — 2026-10-16: account-page composition

The verified lesson-player batch is committed locally as `026424d`. The owner
approved the nine-file account batch, implemented on `codex/account-polish` on
top of that commit. The page keeps learner light/dark themes and existing flows.
Its details, access, password and data sections now have 24px display headings,
consistent rules and spacing. Values wrap long emails, names and server labels.
The password form keeps its existing 24rem measure, and data copy has a readable
measure and relaxed leading. The native export link uses shared secondary control
styles with a measured 44px target. A stale comment denying the existing export
was corrected; no export, password, access or verification behavior was changed.

All 702 frontend tests passed, including three new preservation checks for long
details/server wording, pending password changes and keyboard export access.
The initial production build caught a server/client boundary mistake in shared
export styling. DataExport now uses a small client boundary to call the shared
client control helper; it still prerenders a native anchor without state, click
handler or fetch. After that correction all 35 focused account tests, lint,
TypeScript/production build and four artifact gates pass. Five public routes
remain static; the largest first load is 329.8 KB against 350 KB. The local Django
production-settings deployment check has no issues. Impeccable's detector and
patch whitespace check are clean. Ruff remains unavailable locally; no Python
files changed. Existing metadataBase/Vite and jsdom scrollTo notices remain.

Fourteen final Chrome cases cover desktop/mobile, both themes, both motion
preferences, anonymous/retry states, 320px long content and password pending,
error and success. No horizontal overflow, runtime errors or browser storage
entries were found. Password fields, submit and export follow keyboard order;
keyboard focus rings are visible. The first checker incorrectly evaluated
focus-visible after pointer submissions; it was corrected to use keyboard input
and all fourteen cases passed. Screenshot inspection required no visual changes.

Before/after screenshots and `account-after-review.json` are saved in the local
visualization directory. Account and submission responses are synthetic and
intercepted: no real password, account or export was changed or downloaded.
Real-account/export, Safari/Firefox, physical-device and screen reader checks
remain unverified. The known floating mobile Site map overlap remains unchanged
for the separately proposed shared-navigation batch.

No new dependency, asset, palette, API, billing/access rule or production
configuration is introduced. This account batch remains local and uncommitted;
no push, merge or deployment occurred.

## Latest session — 2026-10-16: lesson-player and transcript polish

The owner approved the six-file learner batch. It is implemented independently
on `codex/lesson-player-polish` from merged master `ca15e80`; course-detail PR #112
remains open with successful frontend/backend CI and dependency audits, while
deployment jobs were skipped. That PR's course changes are not included here.

The player keeps its existing light/dark themes and section title scale. Its
technical course slug is omitted; the existing breadcrumb still returns to the
course. Replay/speed form a named group, the native speed selector has a measured
44px touch target and 16px type, and status/completion stack on mobile. The
transcript uses a quieter border, sentence-case heading, thin active-cue rule,
44px minimum cue targets and wrapping for long unbroken text. Native video,
caption language, seeking, follow scroll, heartbeat, access and completion rules
are unchanged. No new motion, tokens, assets or dependencies were added.

The new control-group regression failed before implementation. All 699 frontend
tests pass, including a new delayed-confirmation test for pending completion.
After the visual correction, all 60 focused player/transcript tests pass again.
Final lint, production build/TypeScript and static/document/CSS/bundle gates pass;
five public routes remain static and the largest first load is 329.8 KB against
350 KB. The local production-settings Django deployment check has no issues.
Impeccable's detector found no issues. Ruff remains unavailable locally (host
Python/API container); no Python files changed. Existing metadataBase/Vite warnings
remain, and the full suite also printed jsdom's unimplemented scrollTo notice.

The first browser pass exposed transcript text extending below its panel. The
flex chain was corrected so the list shrinks and scrolls inside the 32rem cap.
Thirteen final Chrome cases confirm contained scrolling, no horizontal overflow
or runtime errors, visible focus and 44px speed controls. Cases cover desktop and
mobile, both themes, both motion preferences, keyboard seeking, missing transcript,
retry recovery, finished/pending completion and 320px long-content stress.
Screenshot confirmation found the observed transcript issue resolved.

Before/after captures and `lesson-after-review.json` are saved in the visualization
directory. Populated lessons/transcripts, progress and completion responses are
explicitly synthetic and all API requests were intercepted in those cases. The
real local lesson's anonymous view correctly requested sign-in. No real account
or progress was mutated. Real media, Safari/Firefox, physical-device and screen
reader verification remain outstanding. The existing floating mobile Site map
control is unchanged and remains a shared-navigation review item.

The owner authorized committing this verified batch locally. No push, merge,
deployment, production configuration or provider change occurred.

## Latest session — 2026-10-16: registration, verification and recovery

PR #110 is merged with green CI. The owner approved the five-file account-flow
extension, started from merged master `c2fef38` on `codex/account-journal`.
Registration, email verification, reset request and reset redemption now share
sign-in's existing ivory/serif/indigo shell, original illustration and ink detail.
The pathname-selected client layout and quotation panel are replaced by a single
Server Component shell. All form controls precede artwork on mobile; long messages
can wrap. No palette token, new artwork, dependency, API or account behavior changes.

The five scope regressions failed against the previous layout before implementation.
All 72 auth-flow tests and 696 full frontend tests pass. The layout assertions were
then strengthened to require the actual child form field to be visible and present
before hydration; all nine focused layout tests pass. Existing auth security tests
remain intact, including non-enumerating confirmations and URL token privacy.

Frontend lint, production build/TypeScript and all four artifact gates pass. All
five public routes remain static, built document structure and CSS tokens are sound,
and the worst first-load bundle is 329.8 KB against the unchanged 350 KB budget.
Ruff check/format passes across 238 files; the local production-settings Django
deployment check reports no issues. The design detector reports no findings.
The existing local metadataBase fallback warning remains.

Eight before captures and 26 after Chrome cases are saved in the visualization
directory (`auth-extension-before-*`, `auth-extension-after-*`, and their JSON
reports). Desktop/mobile, dark OS preference, reduced motion, long confirmation
text, error/success/resend screens, URL-token views and sign-in regression pass.
No horizontal overflow or runtime page errors were found. All account pages retain
ivory under either OS preference, and form content precedes decorative artwork.
The verification page's keyboard sequence crosses both forms in DOM order, with
solid focus outlines on each tested control. Screenshot review found no material
visual corrections. The first browser attempt reached the prior preview process;
that task-owned process was replaced and all 26 checks ran against the new build.

Account submissions in browser verification use synthetic intercepted responses;
no real account, password or email was changed or sent. Real-account delivery and
Safari/Firefox/physical-device verification remain untested. Loading behavior stays
with the existing shared controls and auth tests. The owner authorized publishing
this verified batch for review on `codex/account-journal`; no deployment is authorized.

No merge, deployment, production configuration change or paid service is included.

## Latest correction — 2026-10-15: conditional theme and native progress

The owner approved the five-file corrective batch after browser review exposed
dark-token hoisting and Chrome's green native progress fill. Dark overrides now
use ordinary `:root` CSS inside the existing media query, leaving all palette
values unchanged. This follows Tailwind's top-level `@theme` requirement:
https://tailwindcss.com/docs/theme. My Courses keeps native progress semantics
with separate WebKit/Firefox track/fill styling and a forced-colors native fallback.

Two new theme/progress tests failed before the fix, then all 94 focused tests
passed. The compiled-CSS gate also rejected the old build. It now requires dark
tokens inside the emitted media rule, rejects unconditional dark-token leakage,
and pins both native progress fill selectors. A negative check injected an
unconditional dark override into an ignored build artifact, observed the gate
reject it, and restored the original bytes. Final browser confirmation ran on
a restarted preview after that restoration.

All 695 frontend tests, lint, production build/TypeScript and four artifact gates
pass. Ruff check/format and the local production-settings deployment check pass.
The first build correctly refused to run without catalogue data while Docker was
off; the existing local services were started, API health returned ok, and the
rebuild passed with real catalogue data. No volume or production data was changed.
The worst first-load bundle is 330.4 KB against the unchanged 350 KB limit.

Seventeen clean Chrome browser cases pass across desktop/mobile, light/dark,
reduced motion, forced colors, empty/error and long-content states. Actual learner
ink/paper now match the requested scheme; progress fills are visibly indigo and
public/sign-in shells retain ivory under either preference. No horizontal overflow,
hidden rows or runtime page errors were found; resume destinations and keyboard
focus remain correct. Forced colors hide ink decoration and use native progress.
Before/after correction captures and JSON reports are saved in the visualization
directory (`my-courses-theme-before-*` / `my-courses-theme-after-*`).

Learner captures use clearly synthetic API fixtures, not real-account authentication
or server authorization evidence. Firefox/Safari runtime checks remain unverified.
No API, palette value, dependency, provider, auth behavior or new motion is changed.
The existing local metadataBase build warning remains. No merge or deployment occurred.

## Latest session — 2026-10-15: My Courses and ink stippling

The owner approved the six-file My Courses proposal and requested additional
black spots to echo the generated artwork. The resulting ten-file batch adds
static semantic-ink stippling to the public footer band, sign-in artwork margin
and My Courses introduction. It uses a CSS SVG mask, not a generated asset;
decorations are non-interactive, aria-hidden and suppressed in forced colors.
Learner light/dark behavior, public ivory and existing imagery remain intact.

My Courses now uses immediately visible ruled rows, responsive native progress
and prominent Start/Continue actions. Empty and anonymous states have distinct
headings and actions. Finished courses include a check beside their text. List
stagger and card hover movement are removed; shared button feedback remains.
API calls, enrollment, resume selection, pagination and retry behavior are unchanged.

Five new regressions failed against the previous implementation, then passed.
All 64 focused course/shell tests and all 693 frontend tests pass. Frontend lint,
production build/TypeScript and all four production-artifact gates pass. Public
routes remain static, document structure and CSS tokens are sound; the worst
first-load bundle is 330.2 KB against the unchanged 350 KB budget. Ruff check and
format pass across 238 files; the local production-settings Django deployment
check reports no issues. The mechanical design detector reports no findings.
The existing local metadataBase build warning remains.

Connected-browser desktop/mobile inspection confirmed the signed-out My Courses
composition, sign-in artwork/spot placement and catalogue decoration. Measured
My Courses, catalogue and sign-in layouts have no horizontal overflow, decorations
are aria-hidden/non-interactive, and keyboard navigation retains a solid outline.
The public fixed-light palette and OS-dark learner palette were seen.

On the owner's next approval to continue verification, the installed Chrome
binary was found at its actual path. The screenshot harness was adapted to screen
readiness rather than network-idle (which timed out). Thirteen after captures and
a JSON evidence report are saved in this chat's visualization directory. Learner
empty/populated/long/error screens use intercepted, explicitly synthetic API
fixtures; they verify rendering, not real authentication or backend authorization.
All measured layouts have no horizontal overflow or page runtime errors. Rows are
immediately visible, resume uses the next lesson (with Next's trailing slash), and
keyboard outlines remain solid. Dark/reduced-motion and light media were emulated.
No complete saved before set exists and no browser/dependency was installed.

**Browser finding, corrected in the batch above:** learner pages stayed dark when
`prefers-color-scheme: dark` is false. Compiled CSS places the dark theme variables
unconditionally in its theme layer: nesting `@theme` inside the source media query
did not preserve that condition. This conflicts with ADR-032/design-system.md's
system theme contract. Existing source/contrast tests and the current artifact
gates did not catch it. Code edits stopped pending the subsequently approved correction plan.
The native Chrome progress bar also remains green despite a computed indigo
`accent-color`; its platform pseudo-elements need explicit styling for the approved
visual treatment. Real-account end-to-end checks remain separate from fixture evidence.

No merge, deployment, backend change or production configuration change is included.

## Earlier session — 2026-10-15: frontend audit remediation

PR #110's frontend/backend tests and backend audit passed; the frontend audit
failed on braces, proxy-addr, sharp and source-map-js. The owner approved the
ten-file remediation plan. Wrangler is pinned at 4.151.0, with Miniflare's sharp
0.35.5; compatible transitive updates resolve proxy-addr 2.0.8 and source-map-js
1.2.2. No new direct dependency, auth behavior or production configuration changed.

The previously approved exact-path audit filter and its tests are now integrated
into this PR. The sole accepted path remains the development-only eslint lint
chain to braces, with the original November 7 review deadline. Raw npm audit still
reports that five-package chain; no zero-vulnerability claim is made. All other
high/critical findings, alternate paths, runtime use, expiry and scanner errors
remain failures. Both audits remain deployment prerequisites.

Before patching, the live filter accepted only braces and rejected the other three
advisories. After patching, the live gate passes with only that accepted path.
All 16 filter tests, 30 CI configuration guards and 688 frontend tests pass.
ESLint and Ruff check/format pass. Local API health and the production-settings
Django deployment check pass. Production build (including TypeScript), static-route,
document-structure, CSS-token and bundle checks pass; live CI results belong to
[PR #110 checks](https://github.com/khafifithebork/e-platform/pull/110/checks).
No merge or deployment is authorized or performed.

---

## Earlier session — 2026-10-14: catalogue discovery

The owner approved the eight-file catalogue batch. Search and filters share a
responsive toolbar, browse/search results use three wider desktop columns, and
shared course cards use larger wrapping titles, quiet borders and no hover lift.
Catalogue result entrances are removed. Real course content, title-only links,
article labels and distinct publication/filter/search empty states are preserved.
Clear search restores keyboard focus and browsing. A new integration regression
test exposed that the prior parent hid courses after a search refusal despite
the child's intended fallback; refusal now restores the current browse listing.
Search debounce, request cancellation, API wording and generated types remain
unchanged. No dependency, new asset, provider or production setting was added.

The initial production build stopped because the local API was offline and Docker
was stuck starting. Troubleshooting stopped after two unsuccessful recovery
attempts. The owner then requested launching Docker and retesting. Desktop was
launched, its engine finished starting, and the existing postgres/redis/storage/api
services started successfully. `/healthz` returns ok; the local container's
production-settings `check --deploy` reports no issues. No Docker volume, database
or production configuration was deleted or changed.

Retest: all 688 frontend tests pass again, including six new recovery/visibility/
content checks. ESLint, production build and TypeScript, static-route, document-
structure, CSS-token and bundle gates pass. Ruff check/format and Git whitespace
checks pass. The existing local metadataBase build warning remains.

Before/after desktop (1440px) and mobile (390px) captures, mobile search-empty and
keyboard-focus evidence are saved in this chat's visualization directory. Browser
checks confirm no horizontal overflow, filter selection/clearing, course navigation,
and empty-search recovery with focus returned to the search input. The local
catalogue has one real published course; multiple-card density and long/optional
content have source/test-fixture evidence only. Current OS-light and fixed-light
editorial behavior were checked; dark/reduced-motion emulation remains unavailable.
The independent reviewer returned `ship` across the approved catalogue scope,
with no material fixes. The review explicitly limits visual certification to the
single-course captures and does not certify preference emulation. The documenter
confirmed the incumbent system guide matches the source and all four captures,
with no further documentation change needed.
The owner requested commit, push and a pull request. The approved frontend work
is committed and pushed on `codex/illustrated-journal` from master, with
[PR #110](https://github.com/khafifithebork/e-platform/pull/110) open for review.
The earlier audit-policy commit remains on its separate branch and is excluded.
No merge or deployment is performed. The PR includes six desktop/mobile captures
and explicitly records the existing master frontend-audit failure.

---

## Earlier session — 2026-10-13: Illustrated Journal sign-in

The owner approved the seven-file sign-in-only batch. `/login/` now reuses C's
fixed-light ivory, ink and indigo semantic tokens, with a serif wordmark/heading
and original companion illustration. Desktop places the form left and art right;
mobile places the complete form and catalogue link before compact art. The form
renders immediately, without an entrance animation. Registration and recovery
retain the prior auth shell; navigation to registration and back was checked.
Login business logic, error messages, session authentication and API types are
unchanged. No dependency, service, migration or production configuration changed.

All 682 frontend tests pass, including eight new shell regression checks.
The focused shell/login/contrast run passed 76 tests. Production build and its
TypeScript check, ESLint, static-route, page-structure, CSS-token and bundle gates
pass. Ruff check/format pass, and the local container's production-settings
`check --deploy` reports no issues. The known local metadataBase build warning
remains. The detector reports no findings; both illustration rasters have prompt
provenance. No backend behavior changed or backend test suite rerun.

Desktop (1440px) and mobile (390px) before/after screenshots are saved in this
chat's visualization directory, along with the mobile API-refusal state. Browser
checks cover visible keyboard focus, long email input, disabled loading controls,
API error recovery, image loading, no horizontal overflow and auth-theme isolation.
The screenshot backend initially scaled the mobile bitmap; recaptures include
viewport-only and full-page evidence with recorded CSS viewport dimensions.
Reduced-motion/theme emulation is unavailable; sign-in has no new animation and
uses the same fixed-light tokens under the current dark OS preference. Login
success and session-storage invariants are covered by existing tests, rather than
a browser login with a real account. Work is local, uncommitted and not deployed.

Independent visual review found the sign-in faithful to C and requested only
correction of the design-system guide's blanket authentication-theme statement.
The documenter updated the incumbent guide; the reviewer scored that fix resolved
and returned `ship` for the scored correction. One stale CSS comment was also
corrected; token values and rules were unchanged. No open material finding remains
in that review list. Git whitespace checks pass. The browser-emulation limitations
above remain outside the review's verified scope.

---

## Earlier session — 2026-10-12: C public palette and shell

The owner requested the full colors and styling of C and approved a ten-file
follow-up. Public routes now use fixed-light ivory #faf7f0, ink #191919 and
indigo #4541b5, serif headings, tighter corners and a plain wordmark/top navigation.
The public sidebar is removed; registration is linked in the footer and AuthMenu
keeps its signed-in destinations. The homepage uses an unframed illustration,
text pricing link and compact centered benefits with dividers. Learner/auth
palettes and navigation are preserved. No dependency or business behavior changed.

All 674 frontend tests passed with two workers. Following the visual review's
root-paper, image-blending and sign-in-selector corrections, all 88 targeted
palette/shell tests passed. Final production build (including TypeScript), ESLint,
static-route, page-structure, CSS-token and bundle checks passed. The reviewer
returned `ship` for all four scored corrections, with no remaining finding in
that fix list. Desktop/mobile homepage, catalogue and pricing screenshots were
confirmed. Keyboard focus, pricing navigation and search empty state were checked;
navigating to sign-in restores the existing dark scheme under the current OS
preference. Reduced-motion browser emulation remains unverified. Work is local,
uncommitted and not deployed.
The code-led review uses C as the direction reference, not a pixel-exact UI image.
Public fixed-light behavior supersedes ADR-032 only for the marketing shell;
ADR-037 and the existing design-system document record that approved decision.

---

## Earlier session — 2026-10-12: homepage direction C

The owner chose C, Illustrated Journal, from the three-direction comparison.
The scoped homepage batch adds an original ink-and-stipple illustration, an
opt-in serif title, and four unboxed benefits before the actual course band.
Indigo controls, global theme tokens, navigation, catalogue and learner behavior
remain unchanged. Hero text and links render visibly before hydration; only the
decorative art has a 280ms entrance. Hero parallax and feature entrances are gone.
ADR-037 and the incumbent design-system document record the scope and provenance.
No dependency, provider, API, migration or deployment changes were made.

Verification: all 655 frontend tests passed with two workers after the concurrent
build/test run hit 11 auth-test failures dominated by timeouts. Assertions and
timeouts were not relaxed. The 14 focused homepage/title tests passed again after
the mobile headline correction. Production build, TypeScript, ESLint, static-route,
page-structure, CSS-token and bundle checks passed; Ruff check/format passed.
The local container's production-settings `check --deploy` reported no issues.
The build retains its local `metadataBase` fallback warning; production readiness
is not implied by the local build or settings check.

Dark-theme desktop/mobile screenshots and keyboard catalogue navigation were
checked. The bounded visual review requested balanced mobile wrapping and updated
documentation; those corrections are applied and confirmed. Final reviewer
disposition: `fix`, with three findings resolved and one documentation convention
unresolved: the skill requests a separate PRODUCT.md. This scoped batch retains
the existing authoritative product documents instead of adding a duplicate.
No visual fixes remain among the reviewer's scored findings.
Light-theme and reduced-motion browser emulation are unavailable in the connected
browser tool. Both-palette contrast tests pass and the shared hydration-safe
MotionProvider is preserved, but those browser checks remain a human verification
gap. No Figma file was supplied; no claim of Figma frame comparison is made.

Before/after screenshots are in the chat's local visualization directory
`2026/10/08/01a11ca8-351f-7c40-b740-d0c88de643fa`. The known dependency audit
findings below remain a separate batch. No merge or deployment was performed.

---

## The quality addendum — eight batches of fourteen areas

**The audit that produced the section below was about accessibility, boundaries and
measurement. This one asks a different question: is this a product a stranger could
actually use.** Fourteen areas were reviewed read-only on 2026-09-28 — trust and
policy pages, multilingual, account and privacy, subscription transparency, course
discovery, learning comfort, brand assets, colour and type, interaction polish,
accessible HTML, SEO, performance, security and operations, and browser
verification. The owner approved **batch one**, then **batch two**, then **batch
three** — which carried the first backend work — then batches **four** through
**eight**, the last of which followed a full re-audit and implemented everything
remaining that needed no owner decision.

**The fourteen areas, counted honestly**, because a single "touched" number has
drifted in this file twice:

- **Seven had work shipped** — account and privacy, course discovery, learning
  comfort, brand assets, interaction polish, accessible HTML, SEO.
- **Two were assessed and needed nothing** — colour and typography (already the most
  examined part of the product), and performance (measured, and re-measured on
  2026-09-30).
- **Five are blocked** on content, a provider, or a decision, not on engineering —
  trust and policy pages, multilingual, subscription transparency, the operational
  half of security and readiness, and browser verification.

**This checklist is not complete and must not be reported as complete.**

*Rows are added after a merge, not before. Written ahead of time they say "open"
for as long as nobody edits them, which happened twice on 2026-09-29.*

| PR | | Merged |
|---|---|---|
| #95 | Batch one — the two emailed tokens, redeemable at last | 2026-09-28 |
| #96 | Batch two — canonical URLs, sitemap, robots, the icon | 2026-09-29 |
| #98 | Batch three — the account page, and a data export | 2026-09-29 |
| #100 | Batch four, part one — captions declare their language | 2026-09-29 |
| #101 | Batch four, part two — playback speed and a replay control | 2026-09-29 |

**Two ADRs — ADR-034 (emailed tokens are pasted) and ADR-035 (canonical URLs and
indexing) — and one dependency bump nobody asked for**, which turned out to be a
pre-existing red gate rather than anything either batch caused. See "The audit gate
was red before either batch touched it" below.

**Also merged earlier: PR #94 and before** — the accessibility audit's own run, which
the next section covers. The addendum is a separate workstream that happens to follow
it, not a continuation of it.

### Batch one — two emailed tokens that could not be redeemed

| Defect | State |
|---|---|
| **`POST /auth/verify-email/` had no caller anywhere in the frontend.** The view, its serializer, its throttle scope and `api.verifyEmail` all existed. No page ever called it, so **no account could be verified through the product at all** | **Fixed** 2026-09-28. New `/verify-email` page |
| **`/reset-password` refused every visit without `?token=`** with a dead-end interstitial. The reset email sends a bare token and no URL, so **that was every real reset** | **Fixed** 2026-09-28. A paste field when the URL carried nothing |

**Both emails send a bare token with no link**, because there is no configured site
URL in `backend/` to build one from — checked rather than assumed. So the pages were
waiting for a link that is never sent. ADR-034 records the decision, including what
sending real links would cost and why that is a backend batch.

**The part worth remembering: a green suite certified a flow that could not be
completed.** `reset-password/page.test.tsx` asserted the dead-end interstitial
appeared and the API was not called. Both assertions were true and the page was
wrong — every test was about the page's own behaviour and none about whether a token
could be redeemed end to end. The two assertions were **replaced**, deliberately,
and the replacement says so in the file.

**What did not get traded away.** The obvious fix is one field prefilled from
`?token=`, and it would have broken a security property both pages already had: the
token must appear nowhere in `innerHTML`, a `value=` attribute included. So the field
appears **only** on the path where the URL carried nothing, and the seam between the
two states is now asserted — without that, "the token is nowhere in the page" could
have been satisfied by a page that simply stopped working. ADR-034 §3.

Also: verification happens on a click and never on mount, because the token is
single-use and React's double-invoked development effects, a refresh or a
back-navigation would each report "not valid" for a token that worked (§4); the copy
said "link" three times for something the email does not contain, and pointed people
at `/login`, where the token is no use; and `verify-email` carries the resend form,
because a failed verification is exactly where a fresh token is needed and
`resend-verification` had no caller either.

**13 provocations, all caught — after one had to be split.** A provocation that
flipped the render condition but left the field's value empty read as a missed
control; the token genuinely was not in the DOM, so that test was right to pass. Two
properties, two provocations, both caught. That is the second time this session a
provocation's own fault first read as a weak test.

**Found while sweeping, not fixed:** `api.lesson`, the by-id lesson fetch, has no
callers since `lessonBySlug` superseded it at M16 T3. Dead rather than broken,
recorded in `docs/specs/frontend-state-and-api.md` §7 and left in place — deleting
code on a hunch is its own hazard.

**A fourth tooling artefact, for the running tally.** `tsc` failed on
`.next/dev/types/routes.d.ts` with three syntax errors. The file was a torn write by
the running dev container — a module closed and then a fragment of a longer previous
version after it — and it changed between two reads. Restored from the clean copy
`next typegen` had just produced. Nothing to do with the code, and it would have
read as one.

### Batch one's own open items

**Nothing here has been run against the live API.** The tests use recorded
responses. An end-to-end pass needs a person: register, copy the token out of
Mailpit, paste it, confirm the account verifies, then the same for a reset. Both
routes are served by the dev container and confirmed rendering
(`/verify-email/` → 200, `<h1>` present, both forms).

**`/verify-email` has never been walked for keyboard order**, and it is the only
page in the product carrying two forms — which is exactly where a tab order goes
wrong. Runbook §3.2 lists it; §6 says plainly that nobody has walked it.

**Two questions for the owner, from ADR-034 §5**, neither of them blocking:

1. **Should the emails send real links?** That is a backend change — a settings
   variable for the frontend's base URL, per environment. If yes, the `?token=`
   branch these pages already have is its destination and only the copy softens
   back toward "link".
2. **The backend's own refusal copy still says "link"** — *"That verification link
   is not valid."* The page displays it verbatim, deliberately, because it must not
   invent a reason the API refused to give. Changing it is a backend edit.

### Batch two — the site had nothing to say to a crawler

**No canonical URL, no sitemap, no robots.txt, no Open Graph, and the favicon was
the Next.js logo** — it arrived with the `create-next-app` scaffold in `66c314b` on
2026-08-14 and nothing ever replaced it, so the browser tab wore the framework's
brand through sixteen milestones. ADR-035.

**The decision was what to say with no domain, because that is this repository's
state.** ADR-025 chose the hosting, not the name. Unset `SITE_URL` now means no
canonical tags, an empty sitemap and `Disallow: /`.

**Not indexed is recoverable; wrongly indexed is not.** That is the whole argument.
The obvious default — falling back to localhost — publishes canonicals pointing at a
machine no crawler can reach, which de-indexes every page *and* looks like it
worked. A value that is set but malformed stops the build instead: a typo is somebody
configuring this and getting it wrong, which is a different situation from nobody
having configured it yet.

**Next's own documentation ruled out the first implementation.** Relative metadata
paths with no `metadataBase` are a *build error*, not a silent omission — so the
naive version of this fail-safe would have broken every build in this repository
today. Recorded in ADR-035 §3 because the failure would have arrived in CI looking
nothing like its cause.

**The canonical is deliberately not on the root layout.** Metadata is inherited, so
one there becomes every route's canonical — `/login` telling crawlers its real
address is `/`. Four public pages carry one, through a helper, and a grep over the
`(auth)`, `(learner)`, `(app)` and `(instructor)` groups asserts none of them grows
one. 13 provocations, all caught.

**Verified against built output, both ways.** With an origin: four canonicals, a
four-entry sitemap, `Host` and `Sitemap` lines. Without one: zero canonical tags
anywhere, an empty `<urlset>`, `Disallow: /`, and no occurrence of `localhost` in any
built page.

**What the build corrected.** A course with an empty description does not ship *no*
description — Next inherits the root's, so `t8-spanish` renders the site description
as its own. Acceptable and now documented where it happens; the code read as if the
tag were absent.

`robots.txt` also stops advertising the authentication routes. Not a control — the
session cookie and the server's checks are that — but an indexed sign-in form is a
phishing lure wearing our name.

**Left out on purpose, each with a reason in ADR-035 §5:** `lastModified` and
`changeFrequency` (no modification time exists; inventing a cadence is inventing a
fact), the Open Graph image (needs its own decision), an `apple-icon` (needs a raster
asset), and `favicon.ico` (deleted — it was the framework's logo and would still
have been served at that path).

**Terms, Privacy and an imprint are not written and not stubbed.** The owner declined
stub routes on 2026-09-28. They need real terms, a real data-protection statement and
a real controller identity for EU learners — an empty policy page reads as a
compliance claim nobody has made. **So "footer completeness" is done only in the
sense that the footer links nowhere false.** That half of batch two is blocked on
owner-supplied content, not on engineering.

### Batch two's own open items

**`SITE_URL` is unset, and the site is therefore deliberately unindexed.** That is
intended behaviour until a domain exists, not a gap — but it is one line away from
being a gap if somebody deploys expecting to be found. The long comment in
`frontend/.env.example` exists for whoever meets that surprise.

**The Open Graph image is undecided**, and it is the one thing that would make a
shared link look like a product rather than a URL. Two routes: `next/og` generating
it at build time, which adds no dependency and keeps the public routes static, or a
drawn static asset. ADR-035 §5 records why neither was improvised.

**A course with no description inherits the site's.** `t8-spanish` is the only
seeded course and its `description` is `""`, so it ships "Curated language courses,
reviewed before publication…" as its own. Acceptable and documented. The better
answer, if anyone wants it, is composing one from facts the API does have — title,
level, language — which is composition, not the invention §6 forbids.

### Batch three — an account surface, and a data export

**Nothing existed at `/account`**, and `POST /auth/password/change/` — the only
authenticated endpoint in the auth group, present since M2 — **had no caller**. That
is the fourth uncalled endpoint this addendum has found, and the pattern is now
recorded: a wrapper in `client.ts` looks like coverage and proves only that somebody
typed the URL. ADR-036.

**The first backend work of the addendum**, because the owner authorised it.

**`AccessSerializer` gained the reason's `label`.** `resolve_account_access` can
return twelve of the fourteen reasons and an account page needs words for all twelve;
a frontend table of them would be a second copy of that vocabulary, which is exactly
what `denial.ts` documents going wrong — `LessonPlayer` branched for nine milestones
on two reasons the server has never sent. `reason` stays the thing to branch on, the
label is the thing to show, and a reason added in M8 arrives with words attached.

**`GET /auth/me/export/`** returns everything the service holds about the signed-in
account, as a JSON download. GDPR Article 15 and 20, which `docs/specs/m10-admin.md`
§6 deferred along with erasure. Export is the tractable half: it destroys nothing and
conflicts with no retention obligation.

**The exclusions are the substance, and one of them is another person's name.**
`AuditLog` is out entirely — every row carries an `actor_label` naming the
administrator who acted, and Article 15 does not extend to other people's data.
`AccessOverride` is in and `granted_by` is not. Also out: password material, token
hashes, `WebhookEvent` (not keyed to a user at all), and course content, which is the
product rather than personal data.

**An existing guard changed the design and was right to.**
`TestNothingElseRederivesAccess` refused the first version, which imported
`Subscription` into the accounts selector — nothing outside `entitlements/` may, because
that import is the seam where a second entitlement rule appears. Strictly a false
positive: the export prints the status and never compares it. **The exemption was still
the wrong fix** (§6 forbids weakening a control to make a test pass), so the reads moved
into `entitlements.selectors.personal_billing_data`. Better layering, arrived at by
being told no.

**Two invented facts were caught before they shipped**, and they are the same mistake
twice. The account page's first draft said "email support" — there is no support
address anywhere in this repository. The export's own `about` text said "See the
privacy documentation" — there is none, that page being blocked on owner-supplied
content. Both now say what is true and point at nothing, and both have tests pinning
the absence. A published channel nobody reads is worse than an admitted gap.

**30 provocations, all caught — after one test turned out not to be a control.**
"States whether access is allowed, from `allowed` and not from the reason" used
fixtures where both readings agree, so replacing the read with the derivation left it
green. `GRACE_PERIOD` and `TRIAL` are grants; keying on `SUBSCRIPTION_ACTIVE` denies a
paying customer mid-grace and every trial user. Fixed and re-provoked. **That is the
third time this week a provocation has found a test that could not fail.**

**Verified against the live API, which is a first for this addendum.** A real session
through the Next rewrite: 200, `Content-Disposition: attachment`,
`Cache-Control: no-store`, all seven sections present, and no `password`, `argon2` or
`token_hash` anywhere in the file.

Four database constraints and one guard caught fixture faults on the way:
`course_published_has_published_at`, `max_position_is_at_least_last`, `AuditLog`'s real
field names, and an assumption that `create_account` issues a verification token. The
query count claimed eight and measured seven — **because the fixture had no
subscription, and `prefetch_related` skips its second query on an empty outer
queryset.** A prefetch cannot be proven by a fixture with no rows.

### Batch three's own open item, and it is not engineering

**Account deletion is not built and not stubbed.** The engineering is the easy part;
what must *survive* an erasure is a set of questions with legal weight, and ADR-036 §5
lists them: invoices against tax retention in a jurisdiction that is itself unresolved
(§11 #1), the audit trail whose only job is to be complete (ADR-018), content an
instructor wrote, and the fact that **there is no contact route for a request to
arrive through**. The page says so out loud and names no channel.

### Batch four — learning comfort, and a completion bug the speed control exposed

**Captions now say what language they are in**, and the blocker that held that since
2026-09-27 was never real — ADR-033 §3a has the full correction. `Transcript.language`
has been a foreign key to `Language` since M6, `LessonTranscript.language_code` was in
the generated types the whole time, and the player fetched that payload on every lesson
load and discarded the field. One serializer field, `language_name`, was the only
backend work genuinely needed. PR #100.

**Then the speed control, and the thing it uncovered.** A playback-rate selector for a
language platform is not a display setting: 0.5× is what lets somebody hear a phrase
they cannot yet parse, and it is arguably the single most valuable comfort feature this
product can have.

**It would have corrupted completion.** The server decides completion as
`watched_seconds >= duration_seconds * LESSON_COMPLETION_THRESHOLD`, so
`watched_seconds` is denominated in *content* seconds — and `watchedSince` returned
wall-clock seconds. At 1× those are identical, which is why nothing noticed for nine
milestones. Once a rate exists it breaks both ways:

- **at 1.5×** a ten-minute lesson is watched through in under seven wall-clock minutes,
  claims under seven, and **never completes**, however many times it is watched;
- **at 0.5×** ten wall-clock minutes cover five minutes of content, so the lesson
  **completes half-heard** — the exact "scrubbed to the end and heard nothing" failure
  ADR-016 §2 was built to prevent, arrived at from the opposite direction.

**And the fix uncovered a second-order one.** Scaling makes the accumulator fractional,
and `watched_delta_seconds` is an `IntegerField`. The client already rounds, so nothing
would have been rejected — it would have **over-claimed half a second on every beat at
1.5×**, two minutes an hour, always in the same direction. The beat now floors and
carries the remainder, and the tests assert totals across four beats, because a single
beat cannot show drift.

**Both controls are buttons and a select, not keyboard shortcuts.** WCAG 2.2 AA 2.1.4
constrains single-character shortcuts — switchable off, remappable, or focus-scoped —
and ADR-030 committed this product to 2.2 AA. Real controls satisfy it by construction
and work on a touch screen, where a shortcut is nothing at all.

**`::cue` is pinned in `assert-css-tokens.mjs`**, and that is the interesting part of
the caption styling. A rule the browser draws inside a shadow tree has no observable
property except having reached the stylesheet: no test can query it, no component
renders it, jsdom has no captions. **CSS has vanished silently from this build twice** —
45 token classes and a whole `@media` block — so the pin is the only thing that would
notice a third time. Provoked by deleting the rule and rebuilding.

**First production use of `localStorage`.** Invariant 9 forbids auth data there, not
preferences — the line ADR-032 §3 drew for a theme. A stored value is validated against
the offered set before it reaches `playbackRate`, where `Infinity` and a negative throw
and `NaN` silently stops playback; storage is not input we control.

12 provocations on the controls, all caught, plus 7 on the captions and the CSS pin
provoked separately.

### Batch four's own open items

**Nobody has watched a video at 0.75× in a browser.** No video provider is configured
(§11 #1 is not the blocker here — M5 shipped a fake provider deliberately), so the
speed control has only ever driven the stand-in clock, which honours the rate by
design. The `<video>` path, `::cue` rendering and the captions menu showing "Spanish"
all need a real provider and a person.

**Caption styling is one `::cue` rule.** Size is left to the browser on purpose, because
caption size is an operating-system accessibility setting and overriding it takes that
control from the people who have already set it.

### Batch five — course discovery, and an empty catalogue that blamed the visitor

**The area was in better shape than its name suggested.** Search (M11, Postgres
full-text with trigram fallback), language and level filters, an honest truncation
notice and a polite live count all existed. Three gaps, and the first is a defect.

**A catalogue with nothing published told its first visitors they had filtered it
away.** One branch served both emptinesses — "No courses match those filters yet. Try
widening one of them" — so the state on the first day after launch, and the state a
build against an empty database produces, pointed people at controls that were not the
problem and implied they had done something. `courses.length === 0` is the honest
signal: it is what the page was *given*, before any filtering, so no combination of
controls can produce it.

**The existing test is why it lasted.** It asserted the component "renders without
crashing" and shows "0 courses" — both true of the wrong message as well as the right
one. Both directions are now pinned, because a component that always said "nothing
published" would mislead just as badly the other way.

**A skill filter, from data that was already on screen.** Every card renders
`skill_areas` as badges and nothing could narrow by them. Options are derived from the
loaded courses for the same reason levels are: a catalogue with no C2 courses should
not offer a C2 filter that always yields nothing.

**`skill_areas` is a free-form `JSONField`** — "e.g. `['listening', 'grammar']`" — so
"Listening" and "listening" are both values two instructors can enter. Tags are grouped
case-insensitively and labelled with the first spelling seen, which gives a usable
filter without pretending the data is tidy. **A controlled vocabulary is the real fix
and it is a backend content decision**, not something a filter should impose quietly.
The generated type is `unknown`, so a malformed row is filtered rather than thrown on —
one bad row must not fail the build for every course.

**Clear filters**, shown only when something is set. 9 provocations, all caught.

**Two things deliberately not done.** The card's skill badges stay non-interactive:
`CourseCard` is pointedly presentational and server-renderable, reused on the landing
and detail pages where filtering makes no sense, and a callback would drag hydration
into all three. And filter state stays out of the URL — invariant 15 forbids
`searchParams` here, and the component already records that the answer, when linkable
filters are wanted, is route segments with `generateStaticParams`. That is an ADR-024
change rather than a tweak.

### Batch five's own open item

**A filtered view still cannot be linked or bookmarked**, which the component has
recorded as a known cost since M15. It becomes worth paying for when somebody wants to
share "B1 Spanish, speaking" — and the fix is route segments, not a query string.

### Batch six — four dead ends that told people to try again and gave them nothing

**Interaction polish turned out to be one finding in four places.** Every failed
load in the application ended with advice:

| Surface | What it said |
|---|---|
| `MyCourses` | "Your courses could not be loaded. Try again in a moment." |
| `LessonGate` | "Something went wrong. Try again in a moment." |
| `AccountDetails` | "Your account could not be loaded. Reloading the page usually fixes it." |
| `LessonPlayer` | "This lesson could not be loaded." |

The common cause of all four is a lapsed connection — **the case where one click
fixes it**. And the `AccountDetails` advice was worse than unhelpful: reloading would
also discard anything typed into the password form below it.

They were three different things on screen, too: a bare `<p className="text-danger">`,
a page-level interstitial, and two `Notice`s. One `LoadFailure` component for all four
is the consistency half of the same fix.

**Retrying re-runs the load, not the page.** Each caller keeps a counter in its
effect's dependency array, so the failed request is repeated while a half-read
transcript, a filtered catalogue or an unsent form stays where it was.

**The button sits outside the live region**, which is the one structural decision.
`Notice` is `role="alert"` with `aria-live="assertive"`; a control inside a live region
can have its label read as part of the announcement, and in some screen-reader
combinations changing its state re-announces the whole region — so pressing "Try
again" would re-read the error at somebody.

**No automatic retry and no backoff.** A component that retried on its own would
hammer an API that is already failing, and the failure a learner actually meets is
their own connection, where the right number of attempts is "when they are back".

`CourseSearch` keeps its inline message and gains a comment saying why, so it does not
read as an omission: the debounce re-fires on the next keystroke, so the retry is
already there.

**A lint rule earned its keep.** The state resets were first written at the top of
each effect, and `react-hooks/set-state-in-effect` objected correctly — an
unconditional `setState` in an effect body costs an extra render on *every* mount to
serve a case that happens rarely. They live in the retry handlers now.

10 provocations, all caught. 613 frontend tests across 49 files.

**Ten files in one change**, which is CLAUDE.md §9's escalation line. Flagged to the
owner before starting and kept together deliberately: splitting it would leave the
application inconsistent between merges, which is the thing the batch exists to fix.

### Batch seven — share images, and a regression the SEO batch had shipped

**ADR-035 §5 had left the Open Graph image and the `apple-icon` out** because
generating one needed a decision and authoring a 180×180 PNG by hand was not something
to improvise. `next/og` answers both: it ships with Next, so nothing was installed, and
an `opengraph-image` route is statically optimized — three routes, three PNGs, all
prerendered, one per published course. ADR-035 §6a.

**Then the finding, which is the reason this batch matters.** `publicMetadata` — added
by the SEO batch itself — **had been stripping `og:site_name` and `og:locale` from all
four public pages since PR #96.**

Next merges metadata *shallowly*: "duplicate keys are replaced based on their
ordering". A page that sets `openGraph` replaces the root layout's whole object, and
that helper set `openGraph: { title, description, url }`. Today it would also have
discarded the `og:image` the new file convention contributes — **three of the four
cards would not have appeared**, and the fourth works only because a course's image is
colocated in the same segment, where file-based metadata outranks the object.

**Found by comparing built HTML, not by reasoning.** `/login`, which sets no
`openGraph`, carried all three tags. `/`, which used the helper, carried none.

**This is the same trap ADR-035 §4 documents, from the other side.** §4 explains why
the root layout must not set a canonical — inheritance would spread it everywhere. The
mirror image, that a page setting a key destroys what it inherited, was not written
down, and the helper written in the same change fell into it.

**Why nothing caught it:** every test written with that helper asserted the fields it
*set*. The fault was in what the object *removed*, which is invisible to anything
reading that object and invisible to a component test, because the framework assembles
metadata. `assert-page-structure.mjs` now checks `og:image` and `og:site_name` on built
HTML, matching pages by shape rather than by slug — and **failing if it matched fewer
than four**, which is the guard on the guard. Both halves provoked.

**Two guards did real work.** `verify:static` refused the course image route until it
declared `dynamicParams = false`; without it the route keeps a dynamic fallback and
becomes server-rendered under `(marketing)`, which the build reports as success either
way. And `seo.test.ts`'s icon guard now also covers `lib/share/card.ts`, which carries
the same brand literals for the same reason — there is no stylesheet inside an
`ImageResponse`.

**Known and accepted:** the cards render in whatever font `ImageResponse` bundles,
because this app ships no web fonts and Satori cannot see system ones. And with no
`SITE_URL` the `og:image` URL falls back to localhost — inert, because that is exactly
the state where `robots.txt` is `Disallow: /`, and correct the moment an origin exists.

10 provocations, all caught. 624 frontend tests across 50 files.

### Batch eight — the unblocked remainder, after a full re-audit

**The addendum was re-audited item by item against the code before anything was
built**, and the result is in this file's own terms: of fourteen areas, the work left
that needed no decision from the owner came to four things. They are done.

**`schema.org/Course` on public course pages.** A course could say its title and
description to a crawler and nothing else; it now says language, CEFR level, skills
taught and instructor — all already stored and already on screen. **The omissions are
the substance**: no `offers` (the price is unresolved, §11 #1, and `offers` is the one
field rendered as a number beside a search result), no `aggregateRating` or `review`
(none exist), no `hasCourseInstance` (needs a schedule; live classes are unapproved),
no `timeRequired` (ADR-007 §4 deferred the aggregate). Each absence is asserted.

**A course title is user-supplied and goes into a `<script>` element**, and §6 forbids
`dangerouslySetInnerHTML` on user content. Checked rather than assumed with a probe
route: React's server renderer emits `Hostile </script>` as `Hostile </\u0073cript>`,
so a plain text child is safe and no exception was needed. That escaping exists only
in server-rendered HTML — jsdom sets text through the DOM, where no parser is involved
— so it is checked on built output instead.

**A link cannot ship pointing at a page that does not exist.** §10 asked for it and
nothing checked it; the fault has been one merge-order away twice. Every internal
`<a href>` resolves to a built file, and `#`, `""`, `/todo` and `javascript:void(0)`
are refused. Two exemptions, both found by running it: `/api/*` is Django behind the
rewrite, and the lesson route is dynamic (ADR-026) — and for that one **only the
unresolvable half is exempt**, so a lesson link still verifies its course was built.

**No positive `tabIndex`**, which was true and unasserted (ADR-023 §1). Worth guarding
because the failure is non-local: one `tabIndex={1}` is visited before every natural
tab stop on the page, not before its siblings.

**A complete cookie and storage inventory**, which decides something rather than
merely recording it: three entries — `sessionid`, `csrftoken`, and one
`localStorage` number for playback speed — and no third-party script of any kind. **So
no consent banner is required today**, and the addendum's instruction not to add one
"purely for appearance" now has evidence behind it. What would change that is written
down: a video provider is the most likely source of a non-essential cookie here, and
**the inventory should be re-run the day one is chosen**.

### What provoking found this time

Four guards were wrong on their first attempt, and each was caught before it shipped:

- The JSON-LD check was pointed at `markup()`, which **strips every `<script>`**
  before the structural checks run — so it matched nothing. The floor asserting it saw
  at least one block is the only reason that surfaced.
- The link check accepted the whole dynamic-lesson pattern, so a link under a course
  that was never built passed.
- The link check's total-count floor did not notice one page losing every anchor,
  because twelve others still had links. It is now per page *and* in total.
- The `tabIndex` guard read files raw, which would have fired the day somebody wrote
  the rule in a comment. `src/test/source.ts` exists because that trap has caught four
  guards here; this is the fifth avoided rather than repeated.

Two provocations were themselves wrong and read as passes until checked: `data-href="`
still contains `href="`, and the landing page's hrefs carry trailing slashes.

### The areas nobody has touched

Recorded by name so the next session does not re-derive the list, and so "two of
fourteen" stays a number rather than an impression. **None of these has been
proposed, let alone approved.**

| Area | What the read-only review noted |
|---|---|
| **Trust and policy pages** | Terms, Privacy, an imprint. Half-addressed in batch two only in the sense that the footer links nowhere false. **Blocked on owner-supplied content** — real terms, a real data-protection statement, a real controller identity for EU learners |
| **Multilingual** — *partly wrong, corrected 2026-10-03* | **The interface half is still deferred** (ADR-033 §4, a named launch locale). **The content half shipped on 2026-10-03** and should never have been in this column: ADR-033 §1 separates four language axes precisely so one can move alone, and this row had collapsed them into one. The transcript panel was failing WCAG 3.1.2 and `native_name` had sat unread in the API since M3. ADR-033 §3b, roadmap D6 |
| ~~**Account and privacy**~~ | **Batch three, 2026-09-29.** `/account` shows what the API knows and changes a password; `GET /auth/me/export/` is the Article 15 export. **Deletion is not built** — ADR-036 §5, and it is a retention question, not an engineering one |
| **Subscription transparency** | Constrained by §11 #1, not by the frontend: no provider, no prices, no self-serve trial. `/pricing` already explains the absence honestly |
| ~~**Course discovery**~~ | **Batches five and eight.** A skill-area filter, a clear control, and a fix for an empty catalogue that blamed the visitor's filters. **Linkable filtered views remain open** — that is an ADR-024 change |
| ~~**Learning comfort**~~ | **Batch four, 2026-09-29.** Captions declare their language, playback speed 0.5×–1.5× persisted per device, a back-5-seconds control, and `::cue` styling. **Nobody has watched a real video at any of it** — no provider is configured |
| ~~**Brand assets**~~ | **Batch seven, 2026-09-30.** A site share card, a per-course card, and the `apple-icon` — all generated at build time by `next/og`, nothing installed. The font does not match the site's, knowingly |
| **Colour and type** | Already the most examined part of the product — ADR-029, `contrast.test.ts`, forced-colours confirmed by the owner. Nothing outstanding found |
| ~~**Interaction polish**~~ | **Batch six, 2026-09-29.** Reviewed, and it was one finding in four places: every failed load dispensed advice instead of offering a retry. The motion system and focus treatment were already settled and needed nothing |
| **Accessible HTML** — *this row was too confident, 2026-10-03* | Markup is covered by ADR-030, axe, `verify:a11y` and the runbook, and the human passes are outstanding as it said. **What it missed: ADR-030 only ever measured the six criteria WCAG 2.2 *adds*.** The ~44 AA criteria it inherits were assumed from a contrast test, and the whole of **1.2 Time-based Media is absent from every document in this repo** — in a video product. ADR-030 §2a, runbook §3.3a, roadmap E7 |
| ~~**Performance**~~ | **Approved and enforced 2026-10-02** — `scripts/assert-bundle-budget.mjs` fails CI above 350 KB first-load per route, with three floors so the script cannot pass by finding nothing. Re-measured after the `next/og` work: worst route 327.4 KB. On `feat/bundle-budget-gate`, **not yet merged** — `master` is red on `braces` |
| **Security and operations** | Sentry, CSP, `_headers`, throttling and lockout all exist. The four moderate advisories above are the live item |

**The honest summary: the seven batches that shipped were the seven areas where
something was actually broken** — two unredeemable tokens, a site invisible to
crawlers, an account with no surface, a player whose captions could not say what
language they were in, a catalogue that blamed its first visitors for being empty,
four failed loads that told people to try again without giving them a way to, and a
metadata helper quietly deleting the tags it did not set.

**Three of the seven were found by a test that passed against the fault it nominally
covered**, and the seventh by a fault that no test in the repository *could* have
seen. That is the pattern worth carrying forward rather than any of the features. The rest is a mix of genuinely blocked
(policy content, billing, caption language), already covered by earlier work, and not
yet looked at properly. Treating them as a single "checklist" would flatten that
difference, which is why they are separated here.

**Three areas remain blocked, not five — recounted 2026-10-03.** Policy content, a
payment provider, and a video provider are the owner's. The previous count of five
included two that have since moved: the **performance budget** was approved and
enforced on 2026-10-02, and **multilingual** was never wholly blocked — its content
half shipped on 2026-10-03 once ADR-033 §1's axes were read properly.

**And the claim "none is blocked on engineering" no longer holds.** Three things are:

- **Audio description and the rest of WCAG 1.2** (roadmap E7) is blocked on *content
  not existing* — not on a decision. It becomes answerable at the first real lesson
  upload, and the answer may carry a per-lesson production cost, which is where the
  owner enters. Until then nobody can say whether the videos need it, because there
  are no videos.
- **Course objectives, prerequisites and total duration** (roadmap E8) are blocked on
  backend modelling: verified 2026-10-03 that `Course` has no such columns and
  `PublicLessonSerializer` exposes no duration. Stating any of them today would mean
  inventing them.
- **The inherited WCAG AA criteria** have never been passed criterion by criterion.
  That is engineering work nobody has scoped.

Colour/type was assessed and found sound. **Accessible HTML no longer belongs in that
sentence** — see its row above.

### Two areas I had written off, re-examined on the owner's question — 2026-10-03

The owner asked what was left of **multilingual, course objectives and audio
descriptions**. All three were in the "nobody has touched" table above as blocked or
deferred. **Checking found that classification wrong in one case, incomplete in
another, and right in the third.**

**Multilingual was wrong, and the ADR I was citing is what makes it wrong.** ADR-033
§1 separates four language axes — interface, learned, instruction, caption+transcript
— and the separation is the point: it exists so one can move without the others. The
owner's deferral covers the *interface*. I had let "localisation is deferred" widen
into "anything with a language in it is deferred", which is the taxonomy's failure
mode rather than its use.

Two real faults were sitting in the axes the deferral left free:

- **`TranscriptPanel` rendered the target language with no `lang` at all.** WCAG 3.1.2
  Language of Parts — a screen reader applied English pronunciation to Spanish. In a
  language-learning product the thing being mispronounced is the thing being taught.
  The value was already in the payload `LessonPlayer` fetched on every lesson load:
  the same `language_code` that D4 put on the `<track>`, one component over, failing
  the same criterion. **Twenty-six passing tests and an axe run sat on top of it** —
  axe cannot know that "Hola, buenos días" is not English, so no tool could have
  found this.
- **`native_name` had been in the API since M3 and nothing read it.** A catalogue for
  an audience "primarily EU and MENA" offered "Spanish" and "Arabic" and never
  "Español" or "العربية" — and for Arabic the English name is a transliteration of a
  different script.

Both fixed, with `lang` **omitted rather than defaulted** when the language is
unknown: inheriting `en` would make a screen reader confident about the wrong
pronunciation, and a wrong `lang` is worse than none. ADR-033 §3b, roadmap D6.

**Audio description was right to be blocked, and for a reason I had not articulated.**
I would have said "owner decision". It is not: whether a video needs description is a
property of the footage, and **there is no footage** — `MediaAsset` rows exist only in
fixtures. The question has no subject, and a fixture would pass the check vacuously.
It unblocks at the first real lesson upload.

Writing that up turned up something larger. **ADR-030 adopted WCAG 2.2 AA having
measured only the six criteria 2.2 *adds*.** The ~44 it inherits were assumed from
`contrast.test.ts`, which computes colour ratios. Grepped before claiming it: **no
document in this repository mentions 1.2.1, 1.2.2, 1.2.3, 1.2.4 or 1.2.5** — the whole
of Time-based Media, in a product whose content is video. 1.2.2 Captions is also
weaker than it looks: the `<track kind="captions">` is fed a *speech* transcript from
Deepgram, and captions must also carry non-speech audio and identify speakers.
ADR-030 §2a, runbook §3.3a, roadmap E7.

**Course objectives, prerequisites and duration were right — backend-blocked.**
Verified rather than assumed: `Course` has no such columns, `PublicLessonSerializer`
exposes no duration. Roadmap E8.

**What the three have in common** is that the classification was recorded without
re-reading the thing it cited. Multilingual cited an ADR that said the opposite; audio
description cited a decision-maker instead of the actual blocker; and the WCAG gap was
invisible because nobody had listed the criteria. The pattern matches ADR-033 §3a's
"blocked on the backend was recorded without reading the backend" — second instance,
and the correction came from a question rather than from review.

### `master` is red on an advisory with no fix — decided 2026-10-03: wait

**The fourth red audit gate in five days, and the first with no mechanical fix.**
`braces` carries a high-severity stack-exhaustion advisory
(GHSA-vfj7-8cjw-p6xm) at **`*` — every published version, including the latest,
3.0.3.** So the `overrides` pin that fixed `js-yaml` has nothing to point at.

One root, entirely dev:
`eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` →
`braces`. `micromatch@4.0.8` is latest and requires `braces ^3.0.3`; every
`fast-glob@3.x` uses micromatch. **There is no version of this chain without the
advisory.**

npm's only offered remedy is `eslint-config-next@14.2.35` — a two-major
**downgrade**, which npm itself flags as breaking, to lint a Next 16 app with a
Next 14 config. Declined.

**Decision: wait for upstream. The gate is not touched.** `master` stays red and
nothing merges until `fast-glob`/`micromatch` move.

The alternatives were both rejected deliberately:

- **`--omit=dev`** would narrow the gate to what ships, and it is the tempting
  one. It would also have hidden the `undici` chain *and* `fast-uri` — both
  dev-only, both worth fixing, one of them a TLS-validation bypass. Narrowing the
  gate to pass today would have retroactively hidden two fixes already made.
- **A per-advisory exception tool** (`audit-ci`, `better-npm-audit`) would give
  the frontend the valve ADR-022 §3 gave the backend — `--ignore-vuln` with a
  comment naming who triaged it, "deliberately more awkward than raising a
  threshold". It costs a §5 dependency decision and is the right answer if this
  recurs or if the advisory turns out to be disputed upstream.

**Practical risk here is close to nil** — stack exhaustion reachable only by
feeding `braces` a deeply nested glob, and the globs come from our own ESLint
config, on developer machines and in CI. That is context, **not** a reason to act
case by case: the gate is severity-based precisely so that judgement is not made
ad hoc, which is ADR-022 §3's whole argument.

**The durable finding, after four of these in five days:** every one came from an
advisory published against code nobody touched. **CI being green is not a property
this repository holds between runs**, and that matters for planning a launch
window more than any individual advisory does.

### The cost of waiting was higher than I said — corrected 2026-10-03

**"The gate is not touched" was right. "Waiting is nearly free" was wrong, and I
did not check before recommending it.**

Opening PR #109 showed what a red audit actually does. The audit was a *step*, and
GitHub stops a job at its first failing step, so the eleven steps behind it came
back **skipped**: type check, lint, the 649 frontend tests, the build, and all four
`verify:*` scripts — including the first-load budget gate added in that same pull
request, whose first act in CI was not to run.

So the situation was not "one red check beside green ones". **CI could not say
whether any change on any branch was correct, for as long as an advisory with no
patched version existed.** Waiting costs the entire pipeline, for an unbounded
period, and I presented it as a cheap option because I reasoned about the
advisory's severity and never looked at the step ordering.

**Fixed by splitting both audits into their own jobs** — `audit-backend` and
`audit-frontend`. The audits are byte-for-byte what they were: same commands, same
thresholds, same editable install, no `continue-on-error`, and both in
`deploy-staging`'s `needs`, so a failure still fails the PR and still blocks a
deploy. The advisory still shows red. It no longer hides everything else.

**The near-miss is the part worth keeping.** The obvious version of that change
leaves `deploy-staging`'s `needs` untouched — which would have removed the audit
from the deploy gate, a security control deleted by a change whose stated purpose
was to strengthen a signal. `test_staging_needs_both_test_jobs` asserted an exact
set, failed, and is the only reason it surfaced. An exact-set assertion looked
pedantic when it was written and was the control that mattered.

Three guards now cover the split, each provoked: no audit command may return to a
job that does other work; neither audit job may be marked `continue-on-error` (a
hole that did not exist while they were steps, and the cheapest possible way to
undo this); and the deploy `needs` set is pinned exactly.

**And the comment trap, seventh instance — caught before shipping for once.** The
"no audit inside the test jobs" guard greps `run:` scripts, and `backend`'s install
step carries a comment containing the literal string `pip-audit`. Read raw, the
guard fails against entirely correct configuration. Verified by removing the
comment-stripping and watching it fail, rather than asserted in a docstring.

ADR-022 §3 carries the amendment.

### PR #109 was merged red, deliberately — 2026-10-04

**`master`'s CI is red and that is a known state, not a regression to investigate.**
`Audit (frontend)` fails on `braces` and will keep failing: the advisory covers `*`,
`3.0.3` is still the newest published version, and there is no patched release to
wait for. Re-checked on 2026-10-04 before merging.

The owner was asked, because "merge once CI passes" was a condition that waiting
could never satisfy, and `master` carries no branch protection — so nothing
mechanical would have stopped the merge. Overridden knowingly; the merge commit
`1713ae3` records why.

**What is green:** `Backend`, `Audit (backend)`, and `Frontend` across all 19 steps.
Before the split, `Frontend` reported eleven of those as skipped.

**Why merging improved the signal rather than spending it.** `master` was already
red on this same advisory, so the merge introduced nothing — and it brought the job
split with it, so `master`'s `Frontend` and `Backend` now actually run. For the
preceding two days `master`'s CI was not red-with-detail, it was dark.

**The next person to see this should not "fix" it** by narrowing the audit. The
remaining open option is the per-advisory exception tool ADR-022 §3 describes — a
frontend equivalent of `--ignore-vuln` with a named triager — which costs a §5
dependency decision and was deliberately not taken. `--omit=dev` remains rejected:
it would retroactively hide the `undici` chain and `fast-uri`.

### A critical RCE in a component added two days earlier — 2026-10-02

**`npm audit` reported `critical`**, the highest severity this repository has seen:
GHSA-vcvr-r3jv-pc5j, remote code execution in `next/og`'s `ImageResponse`, affecting
Next 16.2.0 – 16.3.5. We were on 16.3.3.

**The exposed component was added on 2026-09-30.** Batch seven introduced three
`ImageResponse` routes for the share cards and the apple icon; two days earlier this
advisory would not have described any code here. Nothing was done wrong in adding
them — `next/og` ships with Next and was the right call — but it is a clean example
of how adopting a capability moves the dependency surface, and of why the audit gate
is severity-based rather than a judgement call.

**Our exposure was probably nil, and that is not why it was patched.** All three
routes are statically generated: params come from `generateStaticParams` over our own
database and they render during `next build`, so there is no request-time
`ImageResponse` endpoint to reach. The residual path is build-time — admin-approved
course content flowing into the renderer in CI — which is narrow and still not
somewhere to leave a critical RCE sitting (ADR-022 §3).

Patched 16.3.3 → 16.3.8 for `next` and `eslint-config-next`: a patch-level move
inside 16.3.x, satisfying `@opennextjs/cloudflare`'s declared `next: >=16.3.3`. npm
calls it "outside the stated dependency range" only because the pin is exact. Same
class of action as 2ae9524's `wrangler` bump. **Zero vulnerabilities at every
severity** afterwards.

Verified beyond the usual bar, because a framework bump is not a leaf package: clean
`rm -rf .next` build with all 13 routes keeping their static/SSG/dynamic
classification, the three images still emitted as real PNGs at 1200×630 and 180×180
(magic bytes checked), 636 tests, `tsc`, `eslint`, all three `verify:*`, **the
Cloudflare Worker still builds**, and every route served by the running container.

### Two things this turned up that are worth keeping

**The dev container was still vulnerable after the host was patched.** Its
`node_modules` is an anonymous volume, so `npm install` on the host never reached it —
it kept serving Next 16.3.3 while the lockfile said 16.3.8, and it served *fine*,
which is what makes it easy to miss. Fixed by recreating the container
(`docker compose up -d --build web`), confirmed by reading
`require('next/package.json').version` **from inside** rather than trusting the host.
**A dependency fix is not applied to a running compose stack until the container is
rebuilt**, and the host's lockfile is not evidence about what the container is
running.

**The Worker build failed on the first attempt, and the reason was not Next.**
`.next/dev/types/*` carried a torn write — the generated-types artefact this session
has now hit **five times** — and the build type-checks those files, so it reported
syntax errors that looked exactly like an adapter incompatibility with the new patch.
Clearing `.next/dev` fixed it. Reasoning from the first failure would have concluded
`@opennextjs/cloudflare@1.20.4` could not take Next 16.3.8, which is false and would
have blocked a critical security fix.

### The audit gate was red before either batch touched it

**`npm audit --audit-level=high` failed on PR #96, and not because of PR #96.**
`package.json` and `package-lock.json` on that branch were byte-identical to
`master`, so the same failure was sitting on `master` and on every open branch. Two
advisories had been published upstream against `fast-uri` 3.0.0–3.1.6 — authority
injection via an unvalidated port, and host confusion via an unclosed bracket.

`fast-uri` arrives transitively and build-time only:
`@sentry/nextjs → @sentry/webpack-plugin → webpack → schema-utils → ajv`. Nothing
ships to a browser. It still trips the gate, which is the gate working — ADR-022 §3
set it at `high` precisely so it fires on things worth acting on.

Fixed with `npm audit fix` and **not** `--force`: two patch bumps in the lockfile,
`fast-uri` 3.1.6 → 3.1.8 and `qs` 6.15.3 → 6.16.0, no change to `package.json`.

**Four moderate advisories remain, and they need a decision rather than a command.**
The `undici` one reaches us through `miniflare` and `wrangler`, and clearing it wants
`wrangler@4.101.0` — npm itself flags that as a breaking change, which makes it a
CLAUDE.md §5 call about a deployment dependency and not something to fold into a CI
fix. The gate does not fire on moderate, by ADR-022 §3's own argument, so this will
keep appearing in `npm audit` output without turning anything red. **Worth an owner
decision before M13 rather than during it.**

**The thing to take from this:** a green CI on a feature branch says nothing about
the dependency tree's age, because the audit reads a live advisory database rather
than the diff. Any branch can go red overnight without an edit.

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
| #91 | STATUS: the dependency claim that had gone false, and the defect record by how each was found |

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
| ~~A5 — per-route first-load JS~~ | **Done 2026-09-28, re-measured 2026-09-30**: 314–327 KB gz across twelve routes, still nearly identical. **Seven batches of the addendum cost 1.2–1.6 KB per route**, all of it in shared modules — no runtime dependency moved, which was checked. A 350 KB budget still has 7% headroom; enforcing it needs the owner |
| ~~`<track>`'s `srclang` and `label`~~ | **Done 2026-09-29.** The blocker was not real: `Transcript.language` has been a foreign key since M6 and `language_code` was already in the payload the player fetched |
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
| **`<track>` lacks `srclang` and `label`** | **Fixed 2026-09-29, and it was never blocked.** This row said the value was "not knowable from the frontend because nothing models caption language". `Transcript.language` has been a foreign key to `Language` since M6, and `LessonTranscript.language_code` was in the generated types all along — the player fetched that payload and discarded the field. ADR-033 §3a |

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
| `docs/adr/033-interface-and-learning-languages.md` | Names the four language axes and defers localisation. **§3's `<track>` blocker was wrong and §3a corrects it** — the API had the value the whole time |
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

What remains genuinely undone is verification that needs a person.
`runbooks/accessibility-verification.md` has **five rows** in its log: §3.1 twice,
§3.2's 2.4.11 check, and §3.5 twice — **§3.1 and §3.5 are now complete.** Still
unwalked: the rest of §3.2's keyboard pass, §3.3's screen reader, and §3.4's zoom and
reflow.

**Two of those five rows guard fixes nothing else could have checked.** The forced-colours
one is the clearest case: `outline-none` in Tailwind 4 silently dropped the
transparent-outline fallback a high-contrast mode turns visible, and `outline-hidden`
restored it — a difference **invisible outside such a mode**, so no test in this
repository could ever have shown it holding.

---

## Current milestone

**Still no new product milestone.** The order in CLAUDE.md §10 is unchanged and
nothing has started ahead of it. Everything since M16 has been frontend
consolidation: the redesign's four stages, then the accessibility audit, then the
quality addendum's two batches at the top of this file.

**Where the milestone list actually stands**, stated carefully because this file
contains two different M13 counts and they are snapshots rather than a
contradiction — "6 of 10" under *Previous milestone* is the older one:

- **M0–M12, M15 and M16: complete.** M16 is 9 of 9, M15 is 10 of 10.
- **M13: 10 of 10 with two tasks honestly incomplete.** T8's verification needs a
  Neon branch to run `check_database` against; T10's §2 rollback rehearsal needs a
  registry and an environment. Both say so in their own documents rather than being
  marked done.
- **M14: the unblocked half only.** T7–T10 there and in M13 are unblocked by the
  B-lite decision and **still blocked by the bill** — ADR-025 chose the option, and
  CLAUDE.md §11 #3 is explicit that choosing it is not authorising the spend.

**The four moderate advisories above are worth settling before M13 touches
`wrangler`, not during it.**

**The approved frontend redesign is four stages in and the visual work is done.**
ADR-029 records the Linglee reference and scope. Stage 1 refreshed tokens,
navigation, buttons and cards and gave mobile
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
