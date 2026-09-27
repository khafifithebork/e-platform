# Frontend principles

**Status:** reference. Every rule below is drawn from an accepted decision or from
something this repository learned the hard way.
**Last updated:** 2026-09-27

Fourteen rules, not twenty. Each one exists because breaking it has cost this
project something specific, and each links to its authority. A rule with no
authority is not on this list.

**`CLAUDE.md` outranks this file.** Where they appear to differ, the brief wins.

---

## Data and authority

**1. The frontend presents access decisions; it never makes them.**
`resolve_access` returns a reason, the interface renders it from a typed table, and
**visibility is not authorization** — hiding a control protects nobody. Every gated
read is refused by the server regardless of what the UI shows.
→ CLAUDE.md invariants 3 and 12, ADR-026 §3

**2. Request and response types are generated, never written.**
A hand-written payload type drifts the first time the API changes, and the drift
appears at runtime instead of in the build. CI fails if the schema and the
generated types disagree.
→ CLAUDE.md invariant 16

**3. Echo the API's wording; do not improve it.**
The backend answers identically for a wrong password, an unknown address and a
locked account. Substituting a friendlier message leaks the distinction it went to
trouble to hide. The one message the frontend may invent is "could not reach the
server", because there is no answer to echo.
→ ADR-004, `docs/specs/frontend-state-and-api.md` §4

**4. Nothing auth-related goes into browser storage. Ever.**
Not a token, not a user id, not an email, not an entitlement decision — including
"just to avoid the flicker". The upside shows at logout: there is nothing to clear,
which is the point of the invariant rather than a happy accident.
→ CLAUDE.md invariant 9

---

## Rendering and routes

**5. Public routes stay static, and `searchParams` is how that breaks.**
Reading it in `(marketing)` silently makes the route dynamic. Catalogue filters
therefore live in component state, and a guard looks for `searchParams` by name so
the obvious mistake fails instead. The cost — filtered views are not linkable — is
a consequence of the decision, not an oversight.
→ CLAUDE.md invariant 15, ADR-024, spec §2

**6. Personalisation on a static page resolves in the browser, from a neutral
start.**
The prerendered HTML is identical for everyone. Client components fill in the rest
after hydration, which is also what keeps the B-lite networking question moot: no
Server Component reaches Django.
→ ADR-026 §2, ADR-025

**7. Unknown is not loading, and a 403 is not an error.**
Four states — unknown, loading, empty, error — and collapsing any two is a bug.
Rendering signed-out as a placeholder flashes "Sign in" at every subscriber on
every page load.
→ ADR-026 §2, ADR-031 §4, spec §5

---

## The design system

**8. Reference a token as `(--token)`, never `[--token]`.**
Tailwind 4 compiles the bracket form to an invalid declaration the browser
discards. **45 classes across 15 components had never once applied** before this
was found — invisible to `tsc`, to ESLint and to jsdom. Two guards enforce it, and
a comment counts, because Tailwind cannot tell prose from code.
→ `docs/design-system.md` §1

**9. Never write a sized `<h1>`; never hand-roll a button.**
`PageTitle` and `Button`/`buttonStyles` own those treatments. Fifteen hand-written
titles and five hand-written buttons is how two calls to action ended up 2px
different in height, side by side on the landing page.
→ design-system §3 and §4

**10. Never suppress the focus ring.**
The global ring is written at `:where(...)` zero specificity, so *any*
`outline-none` on an element wins. Where a ring must be visually suppressed on a
large region, use `outline-hidden` — it keeps the `forced-colors` fallback that
`outline-none` in Tailwind 4 drops, which cost the skip-link target its
high-contrast indicator once already.
→ design-system §4, ADR-030 §4

**11. Do not decide reduced motion during render.**
`useReducedMotion()` reads a media query the server cannot. Branching on it made
the server emit `opacity: 0` and a reduced-motion client emit nothing, React
declined to patch the mismatch, and **the landing page rendered blank for exactly
the people who had asked for less motion.** `MotionProvider` decides inside Motion
instead.
→ design-system §6

---

## Accessibility

**12. WCAG 2.2 AA, and an automated pass is not a conformance claim.**
Structure and contrast arithmetic are guarded in CI. Focus visibility, screen
reader behaviour, reflow, forced colours and reduced motion need a person, and the
runbook says how.
→ ADR-030, `docs/runbooks/accessibility-verification.md`

**13. Colour is never the only indicator.**
`Notice` carries a symbol as well as a tone; the current page carries
`aria-current` as well as a style. Both survive forced-colors mode, where the
palette is overridden.
→ design-system §5, ADR-029

---

## Verification

**14. Provoke a guard before believing it.**
A test that has never been seen failing is not known to work. This project's
record is why the rule is here: a reduced-motion test that passed while the bug
shipped because it mocked the hook; a wording assertion that matched a word in a
neighbouring element; a guard compiled into failure by its own docstring; a
whitelist that exempted the very secret it existed to catch; and a provocation
that read as a pass because the substitution never applied.
→ ADR-006, ADR-023 §1

---

## Three habits that are not quite rules

- **Measure before you tidy.** Two "composition passes" in this project found
  almost nothing to compose, and the third found 45 dead classes. Check whether
  the thing is untidy before planning the work. → ADR-023 §1
- **Prefer logical CSS properties.** RTL debt is currently about four utilities;
  it grows with every page. → ADR-033 §2
- **Say what you have not verified.** A green suite proves what it asserts and
  nothing else. The reduced-motion fix has passing tests and has still never been
  seen working in a browser. → ADR-030 §6
