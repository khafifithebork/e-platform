import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import AuthLayout from "./layout";

const route = vi.hoisted(() => ({ pathname: "/login/" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));

describe("the sign-in illustration shell", () => {
  it.each(["/login", "/login/"])("uses the editorial theme at %s", (pathname) => {
    route.pathname = pathname;
    const { container } = render(<AuthLayout><h1>Sign in</h1></AuthLayout>);
    expect(container.querySelector('[data-site-style="editorial"]')).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveTextContent("Sign in");
    expect(screen.getByRole("link", { name: "Back to the catalogue" })).toHaveAttribute("href", "/");
  });

  it("keeps the illustration decorative and after the form in reading order", () => {
    route.pathname = "/login/";
    const { container } = render(<AuthLayout><h1>Sign in</h1><input aria-label="Email" /></AuthLayout>);
    const art = container.querySelector('img[src="/illustrations/sign-in-scene.webp"]');
    expect(art).toHaveAttribute("alt", "");
    expect(art?.closest("aside")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("main").compareDocumentPosition(art!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("renders the form visibly before hydration without an entrance transition", () => {
    route.pathname = "/login/";
    const html = renderToString(<AuthLayout><input aria-label="Email" /></AuthLayout>);
    expect(html).toContain('aria-label="Email"');
    expect(html).not.toMatch(/opacity:0|transform:|animation:/);
  });

  it.each(["/register/", "/forgot-password/", "/reset-password/", "/verify-email/"])(
    "preserves the existing auth shell at %s", (pathname) => {
      route.pathname = pathname;
      const { container } = render(<AuthLayout><h1>Account step</h1></AuthLayout>);
      expect(container.querySelector('[data-site-style="editorial"]')).not.toBeInTheDocument();
      expect(container.querySelector("img")).not.toBeInTheDocument();
      expect(screen.getByRole("main")).toHaveTextContent("Account step");
    },
  );
});
