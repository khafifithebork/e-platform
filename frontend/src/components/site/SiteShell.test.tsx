import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SiteShell } from "./SiteShell";

vi.mock("next/navigation", () => ({ usePathname: () => "/account" }));

beforeEach(() => vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {}))));
afterEach(() => vi.unstubAllGlobals());

it("places the learner navigation toggle before page content", () => {
  render(<SiteShell><section aria-label="Page content">Account form</section></SiteShell>);
  const toggle = screen.getByRole("button", { name: "Site map" });
  const content = screen.getByRole("region", { name: "Page content" });
  expect(toggle.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getAllByRole("main")).toHaveLength(1);
});

it("keeps the editorial shell free of the learner drawer", () => {
  render(<SiteShell variant="editorial">Public content</SiteShell>);
  expect(screen.queryByRole("button", { name: "Site map" })).not.toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Site map" })).not.toBeInTheDocument();
});
