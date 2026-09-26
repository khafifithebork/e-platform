/**
 * Setting a new password from an emailed link.
 *
 * Three things here are claims the page makes about itself and nothing checked:
 *
 * 1. The token "is never rendered into the page and never stored" — it arrives
 *    in a URL, which is the one place a secret in this app is *visible*, so
 *    anything that echoes it back widens the window in which it can be
 *    shoulder-read, screenshotted or logged by a browser extension.
 * 2. A link with no token is refused **without asking the API**, rather than
 *    posting an empty string and showing whatever comes back.
 * 3. The Suspense fallback carries the `<h1>`. `useSearchParams` forces the form
 *    onto the client, so the fallback *is* the prerendered page — M15 T10 fixed
 *    it from being the bare word "Loading…" and left nothing behind to keep it
 *    fixed.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ResetPasswordPage from "@/app/(auth)/reset-password/page";
import { accepted, refusal, stubApi } from "@/test/api";

/** What the emailed link carries. Long and distinctive so a leak is findable. */
const TOKEN = "Zm9yZ2V0dGFibGUtcmVzZXQtdG9rZW4tOTk5";

let search = "";
let suspend = false;
const never = new Promise<never>(() => {});

vi.mock("next/navigation", () => ({
  useSearchParams: () => {
    // Throwing a promise is how a component suspends. This is the only way to
    // reach the fallback from a test: with `useSearchParams` mocked, nothing
    // else in this subtree ever suspends.
    if (suspend) throw never;
    return new URLSearchParams(search);
  },
}));

beforeEach(() => {
  search = `token=${TOKEN}`;
  suspend = false;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function setNewPassword(password = "a long enough password") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/new password/i), password);
  await user.click(screen.getByRole("button", { name: /set new password/i }));
}

describe("the token", () => {
  it("is nowhere in the rendered page", async () => {
    const { container } = render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/new password/i)).toBeVisible());

    // `innerHTML`, not `textContent`: the failure mode worth catching is a
    // `value=`, `href=` or `data-` attribute carrying it, which no visible-text
    // assertion would see.
    expect(container.innerHTML).not.toContain(TOKEN);
  });

  it("is not in storage either", async () => {
    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/new password/i)).toBeVisible());

    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(TOKEN);
  });

  it("does reach the API, which is the only place it should go", async () => {
    // The twin for both tests above: a page that dropped the token entirely
    // would satisfy them and then fail every real reset.
    const fetchMock = stubApi(() => accepted());
    render(<ResetPasswordPage />);

    await setNewPassword();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const [body] = fetchMock.mock.calls
      .filter(([input]) => String(input).endsWith("/auth/password/reset/confirm/"))
      .map(([, init]) => JSON.parse(String(init?.body)));

    expect(body).toEqual({ token: TOKEN, new_password: "a long enough password" });
  });
});

describe("a link with no token", () => {
  it("is refused without asking the API", async () => {
    search = "";
    const fetchMock = stubApi(() => accepted());

    render(<ResetPasswordPage />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: /incomplete/i })).toBeVisible(),
    );
    // Not "the API said no" — the API was never asked. Posting an empty token
    // would spend a rate-limit slot and give the visitor a message about a
    // token rather than about their link.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/new password/i)).toBeNull();
  });

  it("offers a way out rather than a dead end", async () => {
    search = "";
    stubApi(() => accepted());

    render(<ResetPasswordPage />);

    const link = await screen.findByRole("link", { name: /request a new link/i });
    expect(link).toHaveAttribute("href", "/forgot-password");
  });
});

describe("after the password is changed", () => {
  it("says the other sessions are gone, because they are", async () => {
    /**
     * Not cosmetic. The backend flushes every other session on a password
     * change — that is what makes a reset useful after a compromise — and
     * somebody who is not told will assume their other devices are still signed
     * in and read the next sign-in prompt as a fault.
     *
     * **Provoking this took two attempts, and the first one is the note.**
     * Replacing the notice's body text left the test green, which looks like an
     * assertion that cannot fail — until you notice the notice's *title* still
     * said "You are signed out everywhere", so the property genuinely still
     * held. It fails when the claim is actually gone from the state, which is
     * the right sensitivity: it pins what the visitor is told, not which element
     * tells them.
     */
    stubApi(() => accepted());
    render(<ResetPasswordPage />);

    await setNewPassword();

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: /password changed/i })).toBeVisible(),
    );
    expect(screen.getByRole("status").textContent).toMatch(/signed out/i);
  });

  it("stays on the form when the API refused", async () => {
    stubApi(() => refusal(400, "This reset link has expired."));
    render(<ResetPasswordPage />);

    await setNewPassword();

    await waitFor(() => expect(screen.getByText("This reset link has expired.")).toBeVisible());
    expect(screen.queryByRole("heading", { level: 1, name: /password changed/i })).toBeNull();
    expect(screen.getByLabelText(/new password/i)).toBeVisible();
  });
});

describe("the prerendered page", () => {
  it("carries a heading while the client half is still loading", async () => {
    /**
     * The whole static document for this route is the Suspense fallback, so a
     * fallback without an `<h1>` means the served HTML has no title in its
     * heading outline — which is how a screen-reader user establishes where
     * they are before hydration, and what a crawler reads.
     */
    suspend = true;

    render(<ResetPasswordPage />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/choose a new password/i),
    );
  });
});

describe("the heading outline", () => {
  it("titles the form state exactly once", async () => {
    stubApi(() => accepted());
    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/new password/i)).toBeVisible());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("titles the refused-link state exactly once", async () => {
    search = "";
    stubApi(() => accepted());
    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeVisible());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
