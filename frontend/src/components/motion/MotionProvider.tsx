"use client";

import { MotionConfig } from "framer-motion";
import type { ReactNode } from "react";

/**
 * One site-wide answer to "does this visitor want less motion".
 *
 * **This replaces ten render-time branches, and those branches were a bug.**
 * Every animated component used to call `useReducedMotion()` and return a
 * plain element when it was true. The logic was right and the placement was
 * fatal: `useReducedMotion` reads a media query, the server has none, so the
 * server always rendered the *animated* branch with `opacity: 0` inline — and
 * a client that preferred reduced motion rendered the plain branch instead.
 *
 * React reported the hydration mismatch and said exactly what it would do
 * about it: **"This won't be patched up."** The server's `opacity: 0` stayed
 * in the DOM permanently, so the landing page rendered *blank* — headline,
 * subtitle, both calls to action, the course cards and every feature panel —
 * for precisely the people who had asked for less motion, and for nobody else.
 * Measured in a live browser on 2026-09-25, not inferred.
 *
 * **Why a config rather than a fixed branch.** `reducedMotion="user"` moves the
 * decision inside Motion, where it is applied when the animation runs rather
 * than when the tree is rendered — so server and client render identical
 * markup and there is nothing to mismatch. Motion's documentation is specific
 * about what it then does: transform and layout animations are disabled, while
 * *"other animations, like `opacity`... will persist"*. That is the behaviour
 * worth having. Movement is what triggers vestibular symptoms; a fade is not,
 * and a fade is what makes the content appear at all.
 *
 * **The lesson, which cost a passing test.** `motion.test.tsx` asserted the old
 * reduced-motion branch and passed throughout, because it mocked
 * `useReducedMotion`. Mocking the hook made the branch reachable in a test and
 * the bug invisible: no unit test that supplies the value itself can see a
 * fault that exists only in the difference between server and client.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
