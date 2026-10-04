"use client";

import { useMemo, useState } from "react";

import { CourseCard } from "@/components/catalogue/CourseCard";
import { CourseSearch } from "@/components/catalogue/CourseSearch";
import { languageLabel } from "@/components/catalogue/LanguageName";
import { StaggerItem, StaggerList } from "@/components/motion/StaggerList";
import type { Language, PublicCourse } from "@/lib/catalogue/courses";
import type { CourseSearchResults } from "@/lib/catalogue/search";

/**
 * The listing, with its filters.
 *
 * **A client component that receives its data as props, never fetches it.**
 * That is the shape invariant 15 forces: the courses were read at build time
 * by the page above, so they are already in the prerendered HTML. Filtering
 * narrows what is already there.
 *
 * **Abuse case 7 — the content does not need JavaScript.** A client component
 * still prerenders, so a visitor with no JS gets every course in the initial
 * HTML. What they lose is the filtering, which is the correct thing to lose:
 * the catalogue is readable, just not narrowable. A design that fetched on
 * mount would have shown them an empty page.
 *
 * **No `searchParams`, and that is the whole reason state lives here.** Reading
 * a query string in a server component opts the route into dynamic rendering,
 * which is exactly what invariant 15 forbids — and it is the obvious way to
 * build a filter, which is why the structural test on the route group now
 * looks for it explicitly.
 *
 * The cost is real and worth naming: filter state is not in the URL, so a
 * filtered view cannot be linked or bookmarked. When that matters, the answer
 * is filters as route segments with `generateStaticParams` — still static —
 * not a query string.
 */

/** The "no filter" value. A sentinel rather than `""` so the option is real. */
const ANY = "any";

/**
 * A course's skill tags, defensively.
 *
 * `skill_areas` is a `JSONField`, so the generated type is `unknown` and the value
 * is whatever was stored — an array of strings in practice, and not guaranteed to
 * be. `CourseCard` guards it the same way; this is the second reader, which is why
 * it is a function rather than a repeated expression.
 */
function skillsOf(course: PublicCourse): string[] {
  return Array.isArray(course.skill_areas)
    ? (course.skill_areas as unknown[]).filter((tag): tag is string => typeof tag === "string")
    : [];
}

export function CourseCatalogue({
  courses,
  languages,
}: {
  courses: PublicCourse[];
  languages: Language[];
}) {
  const [language, setLanguage] = useState(ANY);
  const [level, setLevel] = useState(ANY);
  const [skill, setSkill] = useState(ANY);

  // Search results replace the browse listing while a query is active, rather
  // than being combined with the filters. Combining them would mean two
  // narrowing mechanisms with different semantics — one ranked and fuzzy on
  // the server, one exact and client-side — and a visitor who filtered to
  // French then searched "spanish" would get an empty page they could not
  // explain. `searching` is tracked separately from `results` so the moment
  // between typing and the first response does not flash the full catalogue.
  const [results, setResults] = useState<CourseSearchResults | null>(null);
  const [searching, setSearching] = useState(false);

  // Levels come from the data rather than a hard-coded CEFR list: a catalogue
  // with no C2 courses should not offer a C2 filter that always yields
  // nothing. Sorted, because Set iteration order is insertion order and that
  // would be whatever the API happened to return.
  const levels = useMemo(
    () => [...new Set(courses.map((course) => course.level))].sort(),
    [courses],
  );

  /**
   * The skill areas this catalogue actually has, for the third filter.
   *
   * Derived from the data for the same reason levels are, and with one extra
   * problem: `Course.skill_areas` is a `JSONField` of **free-form tags** —
   * "e.g. ['listening', 'grammar']" — not a controlled vocabulary. So two
   * instructors can tag the same thing "Listening" and "listening", and a filter
   * built on exact values would offer both, each matching half the courses.
   *
   * Grouped case-insensitively and labelled with the first spelling seen, which
   * gives a usable filter without pretending the underlying data is tidy.
   * **The real fix is a controlled vocabulary**, and that is a backend decision
   * about content modelling rather than something to impose from a filter.
   */
  const skills = useMemo(() => {
    const byKey = new Map<string, string>();

    for (const course of courses) {
      for (const tag of skillsOf(course)) {
        const key = tag.trim().toLowerCase();
        if (key && !byKey.has(key)) byKey.set(key, tag.trim());
      }
    }

    return [...byKey.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([value, label]) => ({ value, label }));
  }, [courses]);

  const visible = useMemo(
    () =>
      courses.filter(
        (course) =>
          (language === ANY || course.language.code === language) &&
          (level === ANY || course.level === level) &&
          (skill === ANY ||
            skillsOf(course).some((tag) => tag.trim().toLowerCase() === skill)),
      ),
    [courses, language, level, skill],
  );

  /** Whether anything is narrowing the list, for the clear control below. */
  const filtered = language !== ANY || level !== ANY || skill !== ANY;

  function clearFilters() {
    setLanguage(ANY);
    setLevel(ANY);
    setSkill(ANY);
  }

  if (searching) {
    return (
      <div className="flex flex-col gap-8">
        <CourseSearch
          onResults={setResults}
          onQueryChange={(q) => setSearching(q.length > 0)}
        />
        <SearchResults results={results} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <CourseSearch
        onResults={setResults}
        onQueryChange={(q) => setSearching(q.length > 0)}
      />

      {/*
       * `<section>` with a label rather than a bare div: filters are a
       * navigable region, and a screen-reader user landing on the page should
       * be able to find them without tabbing through every course.
       */}
      <section aria-label="Filter courses" className="flex flex-wrap gap-4">
        <Select
          label="Language"
          value={language}
          onChange={setLanguage}
          anyLabel="All languages"
          /*
           * `languageLabel`, so the filter offers "Spanish (Español)".
           *
           * A plain string rather than the `LanguageName` component, because an
           * `<option>` renders text only — see that module for what is lost and why
           * a custom listbox is not worth it.
           */
          options={languages.map((item) => ({
            value: item.code,
            label: languageLabel(item),
          }))}
        />
        <Select
          label="Level"
          value={level}
          onChange={setLevel}
          anyLabel="All levels"
          options={levels.map((item) => ({ value: item, label: item }))}
        />

        {/*
         * Only when the catalogue has tags at all. An empty "Skill" select is a
         * control that promises a way to narrow and delivers one option.
         */}
        {skills.length > 0 && (
          <Select
            label="Skill"
            value={skill}
            onChange={setSkill}
            anyLabel="All skills"
            options={skills}
          />
        )}

        {/*
         * Shown only when something is set, and last in the tab order after the
         * controls it undoes. A permanently visible "Clear" on an unfiltered
         * listing is a button that does nothing, which is worse than absent.
         */}
        {filtered && (
          <button
            type="button"
            onClick={clearFilters}
            className="self-end rounded-(--radius-md) border border-line-strong px-3.5 py-2.5
              text-sm text-ink-muted transition-colors hover:border-ink-subtle hover:text-ink"
          >
            Clear filters
          </button>
        )}
      </section>

      {/*
       * The count is announced politely.
       *
       * Changing a filter re-renders the list silently — a sighted user sees
       * it happen, and a screen-reader user gets no signal at all that
       * anything changed. This is the smallest honest fix: one live region
       * saying how many results there now are.
       */}
      <p aria-live="polite" className="text-sm text-ink-muted">
        {visible.length === courses.length
          ? `${courses.length} ${courses.length === 1 ? "course" : "courses"}`
          : `${visible.length} of ${courses.length} courses`}
      </p>

      {/*
       * Two different emptinesses, and conflating them was a real defect.
       *
       * This branch said "No courses match those filters yet. Try widening one of
       * them" for *both* — so a catalogue with nothing published yet told its first
       * visitors to widen filters they had not set, and pointed them at controls
       * that were not the problem. That is the state on the first day after launch
       * and the state a build against an empty database produces, and the existing
       * test only asserted that this component "renders without crashing".
       *
       * `courses.length === 0` is the honest signal: it is what the *page* was given,
       * before any filtering, so no combination of controls can produce it.
       */}
      {courses.length === 0 ? (
        <p className="text-ink-muted">
          No courses have been published yet. They appear here as soon as they are
          reviewed.
        </p>
      ) : visible.length === 0 ? (
        <p className="text-ink-muted">
          No courses match those filters yet. Try widening one of them.
        </p>
      ) : (
        <StaggerList className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visible.map((course) => (
            <StaggerItem key={course.slug}>
              {/* Directly under the page's <h1>, so these are <h2>. */}
              <CourseCard course={course} headingLevel={2} />
            </StaggerItem>
          ))}
        </StaggerList>
      )}
    </div>
  );
}

/**
 * What a search found.
 *
 * `null` means the search has not answered yet — which is why this says
 * nothing rather than "no courses found". Rendering an empty state while a
 * request is in flight tells the visitor their query failed a moment before it
 * succeeds.
 */
function SearchResults({ results }: { results: CourseSearchResults | null }) {
  if (results === null) return null;

  if (results.results.length === 0) {
    return <p className="text-ink-muted">Nothing matched. Try fewer words.</p>;
  }

  return (
    <div className="flex flex-col gap-5">
      <p aria-live="polite" className="text-sm text-ink-muted">
        {results.count} {results.count === 1 ? "result" : "results"}
        {/*
         * The API says when it capped the list, and saying so is the honest
         * thing: a visitor who sees fifty results and assumes that is all of
         * them has been told something untrue by omission.
         */}
        {results.truncated && ` (showing the first ${results.limit})`}
      </p>

      <StaggerList className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {results.results.map((course) => (
          <StaggerItem key={course.slug}>
            {/* Directly under the page's <h1>, so these are <h2>. */}
            <CourseCard course={course} headingLevel={2} />
          </StaggerItem>
        ))}
      </StaggerList>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  anyLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  anyLabel: string;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-ink">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-(--radius-md) border border-line-strong bg-surface
          px-3.5 py-2.5 text-ink shadow-(--shadow-sm) transition-colors
          hover:border-ink-subtle"
      >
        <option value={ANY}>{anyLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
