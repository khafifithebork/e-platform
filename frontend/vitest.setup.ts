/**
 * What every test gets before it runs.
 *
 * Three things now. A setup file that quietly installs mocks is a setup file
 * that makes tests pass for reasons their own source does not show — so each
 * one here is named and reasoned about, not just present.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

type IntersectionObserverCtor = typeof IntersectionObserver;

// React Testing Library mounts into a container it appends to `document.body`.
// Without this, every test's DOM accumulates, `getByRole` starts finding the
// previous test's elements, and the failure lands on whichever test happened
// to run second — the same class of cross-test leak the backend's throttle
// fixture exists to prevent.
afterEach(() => {
  cleanup();
});

/**
 * jsdom implements no `IntersectionObserver` at all — not a stub, not
 * `undefined` behind a feature check, an unthrown `ReferenceError` the moment
 * anything constructs one. `TranscriptPanel` hit the same class of gap for
 * `matchMedia` and guards it locally with a `typeof` check at the call site,
 * which works for a function called conditionally. It does not work here:
 * framer-motion's `whileInView` (`Reveal`, `StaggerList`) constructs the
 * observer as a side effect of mounting, inside the library's own code, so
 * there is no call site in this codebase to guard. A global stub is the only
 * place this can be fixed — every component using scroll-triggered motion
 * would otherwise need its own workaround for a browser API jsdom never
 * intended to implement.
 *
 * A no-op stub, not a fully-behaved fake: nothing under test asserts that a
 * reveal animation actually fired on scroll (that would be a visual claim, not
 * a logic one), only that the element renders. Satisfying the constructor call
 * is all that is needed.
 *
 * **A plain assignment, not `vi.stubGlobal`.** `vi.stubGlobal` registers the
 * stub for `vi.unstubAllGlobals()` to remove — which sounds like the tidier
 * choice until a test file calls it for an unrelated reason.
 * `CourseProgress.test.tsx` does exactly that, in its own `afterEach`, to
 * reset a stubbed `fetch`. That call does not know or care that this file
 * also stubbed `IntersectionObserver`; it clears every tracked stub, and this
 * one would silently vanish after that suite's first test. A direct property
 * assignment is invisible to `vi.unstubAllGlobals()` and survives for the
 * life of the process, which is what a jsdom capability gap needs — it is not
 * per-test state to reset, it is a missing browser API to supply once.
 */
class NoopIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = () => [];
}

globalThis.IntersectionObserver = NoopIntersectionObserver as unknown as IntersectionObserverCtor;
