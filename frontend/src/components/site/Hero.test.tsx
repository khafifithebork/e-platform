import { render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Hero } from "./Hero";
import { PAGE_TITLE, PageTitle } from "@/components/ui/PageTitle";

describe("homepage hero", () => {
  it("editorial_title_does_not_change_other_variants", () => {
    render(<PageTitle variant="editorial">Language courses</PageTitle>);
    expect(screen.getByRole("heading", { level: 1 })).toHaveClass("font-serif");
    expect(PAGE_TITLE.page).toBe("font-display text-4xl leading-tight tracking-tight text-ink");
    expect(PAGE_TITLE.interstitial).toBe("font-display text-3xl leading-tight tracking-tight text-ink");
  });

  it("hero_preserves_navigation", () => {
    render(<Hero />);
    expect(screen.getByRole("link", { name: "Browse the catalogue" })).toHaveAttribute("href", "/courses");
    expect(screen.getByRole("link", { name: "See pricing" })).toHaveAttribute("href", "/pricing");
  });

  it("hero_has_one_accessible_heading", () => {
    render(<Hero />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Language courses, reviewed before they are published.",
    );
  });

  it("artwork_is_decorative_and_reserves_space", () => {
    const { container } = render(<Hero />);
    const art = container.querySelector("img");
    expect(art).toHaveAttribute("alt", "");
    expect(art).toHaveAttribute("width", "960");
    expect(art).toHaveAttribute("height", "960");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("server_render_keeps_text_and_links_visible_without_hydration", () => {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = renderToStaticMarkup(<Hero />);
    for (const element of wrapper.querySelectorAll("h1, a")) {
      let current: Element | null = element;
      while (current) {
        expect((current as HTMLElement).style.opacity).not.toBe("0");
        current = current.parentElement;
      }
    }
    expect(wrapper.querySelectorAll("[tabindex]")).toHaveLength(0);
  });
});
