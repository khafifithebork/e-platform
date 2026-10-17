import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, expect, it } from "vitest";

import { sessionStatus } from "@/lib/auth/session-status";
import { SessionExpiryNotice } from "./SessionExpiryNotice";

beforeEach(() => sessionStatus.finish(sessionStatus.begin("logout")));
afterEach(() => sessionStatus.finish(sessionStatus.begin("logout")));
function end(detail = "Authentication credentials were not provided.") {
  sessionStatus.confirm(sessionStatus.begin());
  sessionStatus.authenticationRequired(sessionStatus.begin(), detail);
}

it("stays silent for unknown and confirmed visits", () => {
  const { container } = render(<SessionExpiryNotice />);
  expect(container).toBeEmptyDOMElement();
  act(() => sessionStatus.confirm(sessionStatus.begin()));
  expect(container).toBeEmptyDOMElement();
});

it("announces the verbatim server detail without moving focus and offers sign-in", () => {
  render(<><button>Keep learning</button><SessionExpiryNotice /></>);
  screen.getByRole("button").focus();
  const detail = "Session ended: <script>plain text</script>";
  act(() => end(detail));
  expect(screen.getByRole("alert")).toHaveTextContent("Sign in to continue");
  expect(screen.getByText(detail)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.getByRole("button")).toHaveFocus();
  expect(document.querySelector("script")).toBeNull();
  act(() => sessionStatus.confirm(sessionStatus.begin()));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("renders neutral static HTML even when the browser observation has ended", () => {
  end();
  expect(renderToString(<SessionExpiryNotice />)).toBe("");
});
