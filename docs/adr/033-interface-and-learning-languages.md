# ADR-033 — Four kinds of language, and deferring localisation without paying for it later

**Status:** accepted by the owner 2026-09-27 (§2 was extracted and fixed the same
day, ahead of the decision on §4)
**Date:** 2026-09-27
**Decides:** the vocabulary for four language axes a language-learning product
confuses at its peril, and what we do *now* so an RTL interface is cheap later
**Depends on:** ADR-014 and ADR-015 (transcription), ADR-024 (static public
catalogue), ADR-026 (the learner surface), ADR-029 (visual refresh), CLAUDE.md §3
(learners primarily EU and MENA) and §5 (no dependency without approval)

---

## Decision

**No localisation, no locale, no dependency — and three cheap habits**, because
the cost of retrofitting them grows with every page written.

| | | Status |
|---|---|---|
| 1 | Name the four axes (§1) and use those names in code and in conversation | reference, in use |
| 2 | Prefer **logical** CSS properties over physical ones | **done 2026-09-27** — §2, six swaps and a guard |
| 3 | Give `<track>` its `srclang` and `label` | **blocked** — §3, the API cannot supply the value yet |

**Localisation is deferred — accepted by the owner 2026-09-27.** No interface
language is committed to, and §4 states the trigger that would reopen it: a named
launch locale, not a possibility.

---

## 1. The four axes

A platform for learning languages has at least four independent languages in play
at once, and conflating any two of them produces bugs that read as nonsense to a
learner. Naming them is most of the value of this ADR.

| Axis | What it is | Today |
|---|---|---|
| **Interface language** | The chrome: navigation, buttons, error messages, "Continue where you left off" | English. `<html lang="en">`, hardcoded in `src/app/layout.tsx` |
| **Learning language** | What the course teaches — the `language` field on a course, which `CourseCatalogue` filters by | Data, already modelled, already filterable (ADR-020) |
| **Content language** | What a lesson's audio and video are actually *in*. Usually the learning language, but a beginner course explains in the learner's language | Not modelled separately |
| **Caption language** | What a `TranscriptSegment` row holds, and therefore what the VTT projection is in | Not modelled separately from content |

**The distinction that matters most is interface versus learning.** A German
speaker learning Arabic wants a German interface and Arabic content. Get that
backwards and you have an Arabic interface for someone who cannot read it yet —
which is the entire product's subject matter, inverted.

**The one with a live consequence is caption language**, see §3.

---

## 2. Logical properties — **extracted and fixed 2026-09-27**

`lang="en"` is hardcoded and there is no `dir` attribute anywhere. That is
correct for an English-only product and says nothing about the future.

What did say something was the class inventory. The original estimate, written
before the fix and kept because the correction is the useful part:

> **11** physical-direction utilities against **0** logical ones, of which "about
> four would actually be wrong in an RTL interface" — `Curriculum`'s indent,
> `TranscriptPanel`'s cue marker and scrollbar gutter, and `Field`'s "(optional)"
> marker.

**Split out of this ADR at the owner's instruction**, on the same reasoning that
split ADR-032: switching a utility needs no product decision, while §4's deferral
of localisation does. Fixed in three components and pinned by
`src/test/logical-properties.test.ts`.

### The count above was wrong, in the direction estimates usually are

"About four" was an estimate from a partial read. Counted properly with a pattern
rather than by eye, there were **nine**, and they split into two kinds:

**Six are content flow, and all six are now logical** — `Curriculum`'s nesting
indent and its accordion label, `TranscriptPanel`'s cue marker, scrollbar gutter
and cue text, and `Field`'s "(optional)" marker. `ps-`/`pe-`/`ms-`/`border-s`/`text-start`
are the same length as what they replaced and behave identically in LTR, so this
cost nothing.

**Two are navigation chrome, and they stay physical.** `SiteNavTree` closes the
desktop rail and the mobile drawer with `border-r` while both are anchored to the
left edge — the drawer at `left-0`, sliding in from `-100%`. Making those logical
is not a utility swap: it flips which side the navigation lives on, which border
closes it, and which way the animation travels. **ADR-029 accepted a left rail**,
so that is a layout decision and belongs to whoever revisits it.

They are **pinned, not exempted**: the guard asserts the physical set is exactly
those two, so removing them fails just as adding a new one does. An exemption list
silently absorbs the next offender; a pinned set makes either direction a
deliberate edit to a test.

`left-` and `right-` insets are deliberately not covered. They position against
the viewport — the skip link, the drawer edge, the hero's decorative cards — and
physical is correct there. A rule catching those would fire on code that is right.

### What was verified, and the third tooling artefact of the session

**Verified:** the emitted CSS uses genuine logical properties —
`padding-inline-start`, `border-inline-start-width`, `margin-inline-start`,
`text-align: start`, read out of the compiled stylesheet. And **LTR rendering is
unchanged**: the curriculum indent still computes to `padding-left: 16px` with a
left border, exactly as `pl-4 border-l` did, checked in a browser against a
`rounded-full` control.

**Not verified: the RTL flip**, and the reason is the tooling. Setting `dir="rtl"`
made `direction` compute to `rtl` while the physical mapping did not move. That
looked like the swap having achieved nothing — until an isolated probe showed a
bare element with an **inline** `padding-inline-start: 16px` also fails to flip
when `dir` is set directly on it. **This browser does not re-resolve logical
properties on a direction change**, so it cannot demonstrate the behaviour either
way.

That is the third artefact of this kind in one session, after a frozen
`requestAnimationFrame` and a stylesheet that had not loaded reporting every
radius as `0px`. Each initially read as a bug in the code. **Isolate before
concluding** — the cost of not doing so here would have been reverting a correct
change.

---

## 3. The `<track>` element is missing two attributes

`LessonPlayer` renders:

```
<track kind="captions" src={`/api/v1/lessons/${lessonId}/transcript.vtt`} default />
```

**That is right in the part that matters** — captions come from the VTT
projection of `TranscriptSegment` rows, never a stored file (invariant 13,
ADR-014) — and it is wired, which is more than many products manage.

It is missing `srclang` and `label`:

- **`srclang`** is the caption track's language. Without it a browser and an
  assistive technology have no way to know what language the captions are in, and
  nothing can offer to translate them or announce them correctly. This is WCAG
  3.1.2 Language of Parts territory once captions are in a different language from
  the page.
- **`label`** is what the browser's captions menu shows. Without it the learner
  picks from an unnamed entry.

**And a question that has to be answered before either can be filled in:** the API
does not expose the caption language. Nothing in the generated types carries it,
because nothing models content or caption language separately from the course's
learning language.

So the correct value for `srclang` is **not currently knowable from the
frontend.** Guessing it — say, from the course's learning language — would be
wrong for exactly the courses that matter most: a beginner course whose captions
are in the learner's language, not the one being taught.

**This is therefore a backend-visible gap**, and the honest sequence is: model it,
expose it in the schema, regenerate types, then fill in the attributes. Hardcoding
`srclang="en"` today to satisfy a validator would be a fabricated fact about
content nobody has checked. Recorded here, not fixed here.

---

## 4. What would justify revisiting localisation

**A named launch locale from the owner.** Not "we might support Arabic" — a
decision that release *N* ships an Arabic or French interface. Until then:

- No `next-intl`, no `react-i18next`, no message catalogue. §5 approval, and the
  wrong library chosen early is harder to remove than absent tooling is to add.
- No route-based locale segmentation. `[locale]` in the path changes every route,
  interacts with ADR-024's static generation and with the rewrite ADR-001 §2.1
  describes, and is expensive to undo.
- **No machine-translated interface strings.** For a product whose subject is
  language, an interface with awkward grammar is a claim about our competence.

When a locale is named, the work is: a message catalogue, `lang` and `dir` set per
request on `<html>`, a locale-aware `Intl` pass (`formatPrice` already leaves the
locale undefined and uses the visitor's own — deliberately), the four utilities in
§2 if they are still physical, and a font review for script coverage. The system
stack in `layout.tsx` covers Latin well; **Arabic script coverage on Windows,
macOS, Android and iOS system fonts has not been checked**, and that is a real
piece of work rather than a footnote.

---

## Consequences

**Positive.** The four axes stop being conflated in conversation and in code
review. RTL debt is capped at roughly four utilities instead of growing per page.
A real defect in the captions track is recorded with its actual blocker rather
than patched with a guess. No dependency, no locale assumed, no scope added.

**Negative.** Logical properties are less familiar and a contributor will reach
for `ml-` by habit; the cost is a review comment, and no guard is proposed because
a lint rule banning physical properties would fire on the legitimate cases in §2.
And §3 records a defect this ADR cannot fix, which means the captions menu stays
unnamed until the backend models caption language.

**UX.** Nothing visible today. The `<track>` fix is the one user-facing item and
it waits on the schema.

**Accessibility.** `lang` on `<html>` is 3.1.1 and is already correct. 3.1.2
Language of Parts becomes relevant the moment content and interface languages
differ, which is exactly this product — and §3 is why we cannot yet satisfy it.
`docs/runbooks/accessibility-verification.md` §3.4 covers text expansion, the
proxy for localisation until there is one.

**Security and performance.** None. No library, no bundle change. Worth noting
that *not* adding a localisation framework keeps the client bundle where §8 of
`docs/specs/frontend-state-and-api.md` measures it.

---

## Implementation guidance

- Switch the four sites in §2 to logical equivalents; leave the other seven.
- Prefer `ms-`/`me-`/`ps-`/`pe-`/`start-`/`end-` and `text-start`/`text-end` in new
  code. Physical is correct for viewport-anchored and decorative positioning; say
  so in a comment when you use it deliberately.
- Do **not** add `dir` to `<html>` yet. A hardcoded `dir="ltr"` is noise, and a
  dynamic one needs a locale that does not exist.
- Do not touch `<track>` until the API exposes a caption language.

## Verification criteria

1. ~~The four utilities are logical.~~ **Done** — six of them, and `npm test`,
   `verify:a11y`, `verify:static` and `verify:css` all still pass. LTR rendering
   confirmed unchanged in a browser.
2. ~~A grep in review, not a guard.~~ **Superseded: there is a guard**,
   `src/test/logical-properties.test.ts`, which turned out to be possible because
   the physical set left over is exactly two and can be pinned rather than
   exempted. Provoked in both directions.
3. **Outstanding:** the RTL flip itself, which this browser cannot demonstrate —
   see §2. A person with a real browser and `dir="rtl"` closes this.
4. §3 stays open until the schema carries caption language. Listed as a gap in
   `docs/STATUS.md` and as roadmap D4, not silently closed.

## Related

ADR-014, ADR-015 (transcripts are rows; VTT is a projection), ADR-020 (language as
a catalogue filter), ADR-026, ADR-030, `docs/design-system.md`,
`docs/runbooks/accessibility-verification.md`.

**Approval:** granted by the owner on 2026-09-27, deferring localisation. §2 had
already been split out and fixed the same day, as with ADR-032 §2.

**What deferral does not mean.** It does not mean the product is English-only
forever, and it does not license writing English-only assumptions into the code —
§2's habit is precisely so that it stays cheap to change. Nor does it close §3:
`<track>` still lacks `srclang` and `label`, that is a defect rather than a
decision, and it is **blocked on backend modelling** (roadmap D4) because the
correct value is not knowable from the frontend. Deferring the interface language
and failing to say what language the captions are in are different problems, and
only one of them is settled here.
