/**
 * What every test gets before it runs.
 *
 * Two things only. A setup file that quietly installs mocks is a setup file
 * that makes tests pass for reasons their own source does not show.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// React Testing Library mounts into a container it appends to `document.body`.
// Without this, every test's DOM accumulates, `getByRole` starts finding the
// previous test's elements, and the failure lands on whichever test happened
// to run second — the same class of cross-test leak the backend's throttle
// fixture exists to prevent.
afterEach(() => {
  cleanup();
});
