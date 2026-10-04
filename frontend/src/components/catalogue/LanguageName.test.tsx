/**
 * Naming a language in English and in its own language.
 *
 * `native_name` has been in the API since M3 and nothing read it. The tests that
 * matter are not "does it render the string" — they are the two attributes, because
 * those are what make it correct rather than decorative, and they are exactly what a
 * later tidy-up would strip as noise.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LanguageName, languageLabel } from "@/components/catalogue/LanguageName";
import type { Language } from "@/lib/catalogue/courses";
import { axeViolations } from "@/test/axe";

const SPANISH: Language = { code: "es", name: "Spanish", native_name: "Español" };
const ARABIC: Language = { code: "ar", name: "Arabic", native_name: "العربية" };
const ENGLISH: Language = { code: "en", name: "English", native_name: "English" };

describe("the element form", () => {
  it("names the language both ways", () => {
    const { container } = render(<LanguageName language={SPANISH} />);

    expect(container.textContent).toBe("Spanish (Español)");
  });

  it("marks the native name with its own lang", () => {
    /**
     * **WCAG 3.1.2 Language of Parts, and the point of the component.** "Español"
     * inside an English document is read with English pronunciation rules unless it
     * says otherwise — and announcing a language's own name wrongly is a particularly
     * poor way to label it.
     */
    render(<LanguageName language={SPANISH} />);

    const native = screen.getByText("Español");

    expect(native).toHaveAttribute("lang", "es");
  });

  it("lets the browser decide direction, for right-to-left names", () => {
    /**
     * `dir="auto"` rather than a code-to-direction table of our own. The browser reads
     * the first strong directional character in the text, which is correct for Arabic
     * and Hebrew without this component holding a list it would have to maintain —
     * and ADR-033 deferred the interface RTL work, so inventing such a list here
     * would be building the deferred thing by accident.
     */
    render(<LanguageName language={ARABIC} />);

    const native = screen.getByText("العربية");

    expect(native).toHaveAttribute("lang", "ar");
    expect(native).toHaveAttribute("dir", "auto");
  });

  it("says a name once when both names are the same word", () => {
    // "English (English)" is noise. The twin for the tests above: a component that
    // always rendered the pair would pass all of them.
    const { container } = render(<LanguageName language={ENGLISH} />);

    expect(container.textContent).toBe("English");
  });

  it("falls back to the English name when the native one is missing or blank", () => {
    // The API types `native_name` as a plain string, so empty is possible — a
    // language row whose native name was never filled in.
    for (const native of ["", "   ", undefined as unknown as string]) {
      const { container, unmount } = render(
        <LanguageName language={{ ...SPANISH, native_name: native }} />,
      );

      expect(container.textContent).toBe("Spanish");
      unmount();
    }
  });

  it("has no axe violations in either script", async () => {
    const { container } = render(
      <p>
        <LanguageName language={SPANISH} /> <LanguageName language={ARABIC} />
      </p>,
    );

    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("the string form, for an <option>", () => {
  it("pairs the names", () => {
    expect(languageLabel(SPANISH)).toBe("Spanish (Español)");
  });

  it("says a name once when they match, and when the native one is blank", () => {
    expect(languageLabel(ENGLISH)).toBe("English");
    expect(languageLabel({ ...SPANISH, native_name: "" })).toBe("Spanish");
  });

  it("carries no markup, which is the documented loss", () => {
    /**
     * An `<option>` renders text only, so the `lang` and `dir` the element form sets
     * cannot go inside it. Asserted rather than left implicit, so the limitation is
     * visible to the next reader instead of looking like an oversight — and so that
     * anybody "fixing" this by returning JSX finds out here that `<option>` cannot
     * take it.
     */
    expect(languageLabel(ARABIC)).toBe("Arabic (العربية)");
    expect(languageLabel(ARABIC)).not.toMatch(/[<>]/);
  });
});
