"use client";

import { useMemo, useState } from "react";

import { CourseCard } from "@/components/catalogue/CourseCard";
import { CourseSearch } from "@/components/catalogue/CourseSearch";
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

export function CourseCatalogue({
  courses,
  languages,
}: {
  courses: PublicCourse[];
  languages: Language[];
}) {
  const [language, setLanguage] = useState(ANY);
  const [level, setLevel] = useState(ANY);

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

  const visible = useMemo(
    () =>
      courses.filter(
        (course) =>
          (language === ANY || course.language.code === language) &&
          (level === ANY || course.level === level),
      ),
    [courses, language, level],
  );

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
          options={languages.map((item) => ({
            value: item.code,
            label: item.name,
          }))}
        />
        <Select
          label="Level"
          value={level}
          onChange={setLevel}
          anyLabel="All levels"
          options={levels.map((item) => ({ value: item, label: item }))}
        />
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

      {visible.length === 0 ? (
        <p className="text-ink-muted">
          No courses match those filters yet. Try widening one of them.
        </p>
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((course) => (
            <li key={course.slug}>
              {/* Directly under the page's <h1>, so these are <h2>. */}
              <CourseCard course={course} headingLevel={2} />
            </li>
          ))}
        </ul>
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

      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {results.results.map((course) => (
          <li key={course.slug}>
            {/* Directly under the page's <h1>, so these are <h2>. */}
            <CourseCard course={course} headingLevel={2} />
          </li>
        ))}
      </ul>
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
        className="rounded-[--radius-sm] border border-line-strong bg-surface
          px-3 py-2 text-ink"
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
