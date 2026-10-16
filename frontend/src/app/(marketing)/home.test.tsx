import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import Home from "./page";

afterEach(() => vi.unstubAllGlobals());

it("homepage_preserves_verified_features_when_catalogue_is_empty", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([]))));
  render(await Home());
  for (const feature of [
    "Video, audio and written lessons",
    "Transcripts and subtitles",
    "Progress that follows you",
    "Reviewed, not just uploaded",
  ]) {
    expect(screen.getByText(feature)).toBeInTheDocument();
  }
  expect(screen.queryByRole("heading", { name: "Recently published" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Browse the catalogue" })).toBeInTheDocument();
});
