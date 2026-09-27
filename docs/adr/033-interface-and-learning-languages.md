# ADR-033 — Four kinds of language, and deferring localisation without paying for it later

**Status:** proposed
**Date:** 2026-09-27
**Decides:** the vocabulary for four language axes a language-learning product
confuses at its peril, and what we do *now* so an RTL interface is cheap later
**Depends on:** ADR-014 and ADR-015 (transcription), ADR-024 (static public
catalogue), ADR-026 (the learner surface), ADR-029 (visual refresh), CLAUDE.md §3
(learners primarily EU and MENA) and §5 (no dependency without approval)

---

## Decision

**No localisation, no locale, no dependency — and three cheap habits adopted
today**, because the cost of retrofitting them is currently about four utility
classes and it grows with every page written.

1. Name the four axes (§1) and use those names in code and in conversation.
2. Prefer **logical** CSS properties over physical ones from here on.
3. Fix the `<track>` element, which is missing `srclang` and `label` — a defect,
   not a preference.

**Deliberately not decided:** which interface languages we will support, when, or
with what library. §4 states the trigger.

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

## 2. Logical properties, starting now

`lang="en"` is hardcoded and there is no `dir` attribute anywhere. That is
correct for an English-only product and says nothing about the future.

What does say something is the class inventory. Measured across `src/`:

- **11** physical-direction utilities (`ml-`, `pl-`, `pr-`, `left-`, `right-`,
  `text-left`)
- **0** logical ones (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`)

Of the 11, most are genuinely direction-independent and would be wrong to change:
the decorative hero cards are absolutely positioned art, the drawer is anchored
to one edge by design, the skip link's `focus:left-4` is a viewport position.

**About four would actually be wrong in an RTL interface:**

| Site | Class | In RTL |
|---|---|---|
| `Curriculum.tsx:116` | `border-l pl-4` | The nesting indent appears on the wrong side |
| `TranscriptPanel.tsx:83` | `border-l-2` | The active-cue marker moves to the wrong edge |
| `TranscriptPanel.tsx:75` | `pr-1` | Scrollbar gutter on the wrong side |
| `Field.tsx:47` | `ml-1.5` | The "(optional)" marker detaches from its label |

**Four utilities is the entire RTL debt today.** That is the argument: the
decision to localise can wait, but the *habit* cannot, because the debt is
proportional to how many pages get written before it starts. Switching those four
now and preferring logical properties from here on costs nothing and is not a
speculative abstraction — `ms-`/`me-`/`ps-`/`pe-` are the same length as what they
replace and behave identically in LTR.

`text-left` is a special case: in a `<button>` whose text must align with its
label it is usually `text-start` that was meant, and in a code or number context
it genuinely is left. Decide per site rather than replacing mechanically.

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

1. The four utilities are logical, and `npm test` plus `verify:a11y` still pass —
   this is a no-op in LTR, so any visible change means one was mis-swapped.
2. A grep in review, not a guard: new physical-direction utilities should be
   deliberate and commented.
3. §3 stays open until the schema carries caption language. It is listed as a gap
   in `docs/STATUS.md`, not silently closed.

## Related

ADR-014, ADR-015 (transcripts are rows; VTT is a projection), ADR-020 (language as
a catalogue filter), ADR-026, ADR-030, `docs/design-system.md`,
`docs/runbooks/accessibility-verification.md`.

**Approval required:** the owner. The habits in §2 need no product decision; §4's
deferral does, because it declines to plan localisation; §3 needs backend work
that is not scheduled and belongs to whichever milestone owns caption metadata.
