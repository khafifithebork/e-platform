import type { Language } from "@/lib/catalogue/courses";

/**
 * A language named in English and in its own language.
 *
 * **`native_name` has been in the API since M3 and nothing read it.**
 * `LanguageSerializer` returns `["code", "name", "native_name"]`; every component
 * rendered `name` alone, so a catalogue for an audience "primarily EU and MENA"
 * (CLAUDE.md §3) offered "Spanish", "French" and "Arabic" and never "Español",
 * "Français" or "العربية".
 *
 * That matters more here than on a general-purpose site. Somebody looking for French
 * instruction is, by definition, part-way into French — the native name is often what
 * they recognise first, and for Arabic the English name is a transliteration of
 * something written in another script entirely.
 *
 * ## Why this is not blocked on the localisation decision
 *
 * ADR-033 §1 separates four language axes, and the separation is load-bearing: this
 * is the **language being taught**, not the **interface language**. ADR-033 deferred
 * the interface language with a named trigger; it said nothing about labelling the
 * catalogue's own content, and the data for that was already there.
 *
 * **I had treated the whole area as deferred, which was wrong** — the four-axis
 * vocabulary exists precisely so one axis can move without the others.
 *
 * ## The `lang` attribute is the point, not decoration
 *
 * "Español" inside an English document is WCAG 3.1.2 Language of Parts, the same
 * criterion the transcript panel was failing. Without `lang`, a screen reader
 * pronounces it with English rules — and announcing a language's own name wrongly is
 * a particularly poor way to label it. `dir="auto"` because Arabic and Hebrew native
 * names are right-to-left: `auto` lets the browser decide from the text's own
 * characters rather than this component guessing from a code.
 */
export function LanguageName({ language }: { language: Language }) {
  const native = language.native_name?.trim();

  // Nothing to add when the two are the same word — "English (English)" is noise.
  // Also covers a language row whose native name was never filled in; the API
  // documents it as a plain string, so empty is possible.
  if (!native || native === language.name) {
    return <>{language.name}</>;
  }

  return (
    <>
      {language.name}{" "}
      <span className="text-ink-subtle">
        (
        <span lang={language.code} dir="auto">
          {native}
        </span>
        )
      </span>
    </>
  );
}

/**
 * The same pair as a plain string, for places that cannot take an element.
 *
 * A `<select>`'s `<option>` is the case this exists for: it renders text only, so the
 * `lang` and `dir` markup above cannot go inside it. **That is a real loss and not
 * worth hiding** — the option label reads "Spanish (Español)" with no language
 * metadata on the native part, because the element has nowhere to put it. Browsers
 * render option text from the document's direction, so a right-to-left native name in
 * an option may sit awkwardly.
 *
 * Accepted rather than solved: the alternative is a custom listbox, which means
 * rebuilding keyboard and screen-reader behaviour that `<select>` gets right for free.
 * `CourseCatalogue`'s filter uses this; the course page uses the component above,
 * where the markup works.
 */
export function languageLabel(language: Language): string {
  const native = language.native_name?.trim();
  if (!native || native === language.name) return language.name;

  return `${language.name} (${native})`;
}
