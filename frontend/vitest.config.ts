/**
 * Vitest, twelve milestones after CI promised it.
 *
 * `ci.yml` has said "there is no test runner yet — Vitest arrives with the
 * first component in M2" since M0. M2 shipped, six client components exist,
 * and it did not arrive. This is that, and the comment in `ci.yml` is
 * corrected in the same change.
 *
 * Deliberately *not* wired through Next's own test tooling. This project
 * tests two things — pure modules under `src/lib` and components under
 * `src/components` — and neither needs the Next runtime. Keeping the runner
 * independent of the framework means a Next upgrade cannot silently take the
 * test suite with it, which matters here specifically: the OpenNext spike
 * found a two-patch Next upgrade is a prerequisite for B-lite.
 */

import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirrors the `@/*` path alias in tsconfig.json. Vitest does not read
    // tsconfig paths, so without this every `@/lib/...` import resolves to
    // nothing and the failure looks like a missing module rather than a
    // missing configuration line.
    alias: { "@": resolve(__dirname, "./src") },
  },
  test: {
    // jsdom, not happy-dom: `document.cookie` and `Headers` behaviour are
    // exactly what the API client depends on, and jsdom is the implementation
    // whose quirks match browsers more closely.
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // Coverage is not configured here. CLAUDE.md §8 sets coverage targets for
    // backend areas and names none for the frontend; inventing a number would
    // be a gate nobody agreed to. It arrives when there is a target to meet.
  },
});
