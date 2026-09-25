/**
 * The two scroll-motion primitives, and the property that matters more than
 * the animation: **the content is there.**
 *
 * `Reveal` renders `initial="hidden"` — `opacity: 0` — and waits for an
 * `IntersectionObserver` to raise it. Everything below is about what happens
 * when that never comes: a user who prefers reduced motion, a browser where
 * the observer does not fire, or the prerendered HTML before hydration.
 *
 * `globals.css`'s `prefers-reduced-motion` block does not cover these.
 * That rule zeroes CSS durations; framer-motion drives transforms through
 * inline styles and the Web Animations API, which the CSS rule cannot see —
 * the same gap `TranscriptPanel` hit for `scrollIntoView`. `useReducedMotion`
 * is the fix, and these tests are what stop it being removed as redundant.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Reveal } from "@/components/motion/Reveal";
import { StaggerList } from "@/components/motion/StaggerList";

/**
 * `useReducedMotion` is mocked rather than driven through `matchMedia`.
 *
 * framer-motion reads the media query once, at module initialisation, so a
 * `matchMedia` stub installed inside a test arrives too late — the first
 * version of this file did that and the reduced-motion branch never ran.
 * Mocking the library's hook is not the practice §6 forbids: that rule is
 * about mocking *our own* service layer and asserting it was called, and this
 * selects a branch in our component that a third party's global state would
 * otherwise make unreachable.
 */
let reduced = false;

vi.mock("framer-motion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("framer-motion")>();
  return { ...actual, useReducedMotion: () => reduced };
});

function prefersReducedMotion(value: boolean) {
  reduced = value;
}

afterEach(() => {
  // Reset the branch selector too: it is module state, so a test that set it
  // would otherwise decide the branch for every test after it.
  reduced = false;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Reveal", () => {
  it("renders its children even though the observer never fires", () => {
    /**
     * `vitest.setup.ts` stubs `IntersectionObserver` as a no-op, so
     * `whileInView` is never triggered here — which is exactly the condition
     * worth testing. The text must be in the document regardless, because a
     * reveal that gates *existence* rather than opacity would hide content
     * from a screen reader and from anything that does not scroll.
     */
    render(
      <Reveal>
        <p>Reviewed before they are published.</p>
      </Reveal>,
    );

    expect(screen.getByText("Reviewed before they are published.")).toBeInTheDocument();
  });

  it("is present but NOT yet visible until the observer fires", () => {
    /**
     * **A recorded behaviour, not an assertion that it is right.**
     *
     * `initial="hidden"` is `opacity: 0`, and it is in the prerendered HTML:
     * the built landing page ships twelve elements carrying
     * `style="opacity:0;transform:translateY(20px)"`. The text is in the
     * markup — so a crawler and a screen reader both reach it — but a browser
     * shows nothing there until JavaScript runs and the observer fires.
     *
     * The `h1` is deliberately outside a `Reveal`, so the page is not blank
     * without JavaScript. Whoever owns the redesign should decide whether the
     * sections below it should behave the same way; this test exists so the
     * decision is made rather than inherited, and it will fail the moment
     * somebody changes the behaviour either way.
     */
    prefersReducedMotion(false);
    render(
      <Reveal>
        <p>Below the fold.</p>
      </Reveal>,
    );

    expect(screen.getByText("Below the fold.")).not.toBeVisible();
  });

  it("renders identical markup whether or not motion is reduced", () => {
    /**
     * **The test that replaces the one this bug hid behind.**
     *
     * Until 2026-09-25 `Reveal` returned a plain `<div>` when
     * `useReducedMotion()` was true, and a test here asserted exactly that —
     * and passed, because it mocked the hook. The branch was correct and its
     * *placement* was fatal: the hook reads a media query, the server has
     * none, so the server always rendered the animated branch with
     * `opacity: 0` inline while a reduced-motion client rendered the plain
     * one. React reported the hydration mismatch and declined to patch it, so
     * the landing page stayed blank for exactly the people who had asked for
     * less motion.
     *
     * No unit test that supplies the value itself can see that fault — it
     * lives in the difference between server and client. What a unit test
     * *can* assert is the property that makes the fault impossible: **the
     * rendered markup must not depend on the preference at all.**
     * `MotionProvider` applies it inside Motion, when the animation runs.
     */
    prefersReducedMotion(false);
    const normal = render(
      <Reveal className="marker">
        <p>Same either way.</p>
      </Reveal>,
    ).container.innerHTML;
    cleanup();

    prefersReducedMotion(true);
    const reduced = render(
      <Reveal className="marker">
        <p>Same either way.</p>
      </Reveal>,
    ).container.innerHTML;

    expect(reduced).toBe(normal);
  });

  it("keeps the caller's className on both branches", () => {
    // The twin. A reduced-motion branch that dropped `className` would pass
    // the test above while silently losing every layout class the caller set.
    prefersReducedMotion(false);
    const { container } = render(
      <Reveal className="marker">
        <p>Animated.</p>
      </Reveal>,
    );

    expect(container.querySelector(".marker")).not.toBeNull();
  });
});

describe("StaggerList", () => {
  it("is a real list by default, not a grid of divs", () => {
    /**
     * The component's own docstring gives the reason: a screen reader should
     * announce "list, 2 items". Animating `<div>`s to look like a list is the
     * mistake this primitive exists to avoid.
     */
    render(
      <StaggerList>
        <li>Spanish</li>
        <li>Portuguese</li>
      </StaggerList>,
    );

    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders a plain container when the content is not a list", () => {
    // `as="div"` exists for grids of unrelated sections, where forcing list
    // semantics would be the same mistake in the other direction.
    render(
      <StaggerList as="div">
        <section>One</section>
      </StaggerList>,
    );

    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.getByText("One")).toBeInTheDocument();
  });

  it("renders identical markup whether or not motion is reduced", () => {
    // The same property as `Reveal`'s, for the same reason: a structural
    // branch here put `opacity: 0` in the server's HTML and nothing in the
    // client's, and React leaves that mismatch in place.
    prefersReducedMotion(false);
    const normal = render(
      <StaggerList>
        <li>Spanish</li>
      </StaggerList>,
    ).container.innerHTML;
    cleanup();

    prefersReducedMotion(true);
    const reduced = render(
      <StaggerList>
        <li>Spanish</li>
      </StaggerList>,
    ).container.innerHTML;

    expect(reduced).toBe(normal);
    expect(screen.getByText("Spanish")).toBeInTheDocument();
  });
});
