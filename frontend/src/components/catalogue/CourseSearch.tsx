"use client";

import { useEffect, useRef, useState } from "react";

import {
  MIN_QUERY_LENGTH,
  SearchFailed,
  searchCourses,
  type CourseSearchResults,
} from "@/lib/catalogue/search";

/**
 * The search box, and the request it makes.
 *
 * Owns the query and the results; the parent decides what to do with them.
 * That split exists because browsing and searching are two ways of answering
 * the same question and only one of them can be on screen — the parent is
 * where that choice belongs.
 *
 * **Debounced, because the endpoint is throttled at 30/min.** A request per
 * keystroke would exhaust that in eight characters and answer 429 to the
 * visitor for the rest of the minute. The delay is generous rather than
 * snappy for the same reason: this budget is shared with every other anonymous
 * visitor behind the same address.
 */

/**
 * How long a pause in typing counts as "done".
 *
 * 400ms rather than the usual 150–250: the constraint here is the server's
 * throttle, not perceived latency, and a slow deliberate typer at 250ms would
 * still generate a request per word.
 */
const DEBOUNCE_MS = 400;

export function CourseSearch({
  onResults,
  onQueryChange,
}: {
  onResults: (results: CourseSearchResults | null) => void;
  onQueryChange: (query: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  // Derived rather than stored, and that is a correction. The first version
  // kept a `status` state and reset it inside the effect body — which is
  // exactly what `react-hooks/set-state-in-effect` forbids, because a
  // synchronous setState there schedules a second render pass for something
  // that was already computable from the props and state at hand.
  const trimmed = query.trim();
  const tooShort = trimmed.length < MIN_QUERY_LENGTH;

  // Held in a ref rather than state: aborting the previous request must not
  // itself cause a render, and the value is never read during one.
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => {
    onQueryChange(trimmed);

    if (tooShort) {
      // Clearing the box returns the visitor to the full catalogue rather than
      // leaving the last results stranded on screen with an empty search box
      // above them.
      //
      // No setState here: `tooShort` already hides the status line, so there
      // is nothing to reset. `onResults` is a prop, not local state.
      inFlight.current?.abort();
      onResults(null);
      return;
    }

    const timer = setTimeout(() => {
      // The previous request is cancelled before a new one starts. Without
      // this, a slow response to "spa" can land after a fast one to "spanish"
      // and overwrite the newer results — a bug that only appears on a slow
      // connection, which is where nobody develops.
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;

      // Inside the timer callback rather than the effect body, so this is
      // not a synchronous setState during an effect.
      setPending(true);
      searchCourses(trimmed, controller.signal)
        .then((results) => {
          onResults(results);
          setPending(false);
          setError("");
        })
        .catch((cause: unknown) => {
          // An abort is this component working, not failing. Showing an error
          // for a request we cancelled ourselves would make every keystroke
          // flash a message.
          if (cause instanceof DOMException && cause.name === "AbortError") return;

          setPending(false);
          setError(
            cause instanceof SearchFailed ? cause.message : "Search is unavailable right now.",
          );
          // The browse listing stays on screen underneath. A failed search
          // must not take the catalogue down with it.
          onResults(null);
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
    // `onResults` and `onQueryChange` are excluded deliberately: a parent that
    // passes an inline arrow would otherwise re-run this effect — and fire a
    // fresh search — on every one of its own renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trimmed, tooShort]);

  // Abort whatever is in flight when the component goes away, so a response
  // cannot call `onResults` on an unmounted parent.
  useEffect(() => () => inFlight.current?.abort(), []);

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-ink">Search courses</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Try a language, a level, or a skill"
          // `aria-describedby` points at the status line below, so the result
          // count and any error are announced as part of this field rather
          // than as loose text somewhere on the page.
          aria-describedby="search-status"
          className="w-full max-w-md rounded-[--radius-sm] border border-line-strong
            bg-surface px-3 py-2 text-ink placeholder:text-ink-subtle"
        />
      </label>

      {/*
       * One live region for both states.
       *
       * Two would compete: a screen reader announcing "searching" and "3
       * results" from separate regions gives no ordering guarantee. `polite`
       * rather than `assertive` because the visitor is still typing and
       * interrupting them mid-word to say "searching" is worse than silence.
       */}
      <p
        id="search-status"
        aria-live="polite"
        className={`min-h-5 text-sm ${error ? "text-danger" : "text-ink-muted"}`}
      >
        {!tooShort && pending && "Searching…"}
        {!tooShort && !pending && error}
      </p>
    </div>
  );
}
