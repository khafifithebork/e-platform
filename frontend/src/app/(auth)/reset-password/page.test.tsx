/**
 * Setting a new password from an emailed link.
 *
 * Three things here are claims the page makes about itself and nothing checked:
 *
 * 1. The token "is never rendered into the page and never stored" — it arrives
 *    in a URL, which is the one place a secret in this app is *visible*, so
 *    anything that echoes it back widens the window in which it can be
 *    shoulder-read, screenshotted or logged by a browser extension.
 * 2. An empty token is **never posted** — not on arrival, and not when the paste
 *    field is submitted blank. (This was "a link with no token is refused"
 *    until 2026-09-28, when the refusal turned out to be refusing every real
 *    reset. See the block below.)
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
import { axeViolations } from "@/test/axe";

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

/**
 * **This block's behaviour changed deliberately on 2026-09-28, and the old
 * assertions are gone rather than adjusted.**
 *
 * It used to require that a visit with no `?token=` render an interstitial
 * headed "This link is incomplete" and offer a link back to `/forgot-password`.
 * That was a faithful test of the page — and the page was wrong. The reset email
 * (`backend/apps/notifications/templates/email/password_reset/body.txt`) sends
 * the token as bare text with no URL, so *every* real reset arrived here without
 * a query string and was refused. The token had nowhere to go.
 *
 * What survives from the old block is the property that mattered: **the API is
 * not asked with an empty token.** It now holds at submission rather than at
 * render, which is the only place it can hold once there is a field to fill in.
 */
describe("a visit with no token in the URL", () => {
  it("offers a field to paste it into", async () => {
    search = "";
    stubApi(() => accepted());

    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/reset token/i)).toBeVisible());
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/choose a new password/i);
  });

  it("sends the pasted token, and only on submission", async () => {
    search = "";
    const fetchMock = stubApi(() => accepted());
    const user = userEvent.setup();

    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/reset token/i)).toBeVisible());
    // Nothing posted on arrival: rendering a form is not a request.
    expect(fetchMock).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/reset token/i), TOKEN);
    await setNewPassword();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const [body] = fetchMock.mock.calls
      .filter(([input]) => String(input).endsWith("/auth/password/reset/confirm/"))
      .map(([, init]) => JSON.parse(String(init?.body)));

    expect(body).toEqual({ token: TOKEN, new_password: "a long enough password" });
  });

  it("does not post an empty token when the field is left blank", async () => {
    /**
     * The property the old "refused without asking the API" test protected, in
     * the only place it can live now. An empty token cannot succeed —
     * `services.verify_email` and its reset twin short-circuit it so that a
     * digest of the empty string cannot match a stored row — so posting one
     * spends a rate-limit slot on a certain failure and answers with a message
     * about a token rather than about the blank field in front of them.
     */
    search = "";
    const fetchMock = stubApi(() => accepted());

    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/reset token/i)).toBeVisible());
    await setNewPassword();

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/paste the token/i));
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/auth/password/reset/confirm/"),
      ),
    ).toHaveLength(0);
  });

  it("offers a way out rather than a dead end", async () => {
    search = "";
    stubApi(() => accepted());

    render(<ResetPasswordPage />);

    const link = await screen.findByRole("link", { name: /request a new token/i });
    expect(link).toHaveAttribute("href", "/forgot-password");
  });

  it("has no axe violations, with the error showing", async () => {
    // The state this change introduced, in the variant that carries the ARIA:
    // `aria-invalid` on the token field and `aria-describedby` pointing at both
    // its hint and its error.
    search = "";
    stubApi(() => accepted());

    const { container } = render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/reset token/i)).toBeVisible());
    await setNewPassword();

    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("a link that did carry a token", () => {
  it("does not show the paste field, because prefilling it would render the token", async () => {
    /**
     * The two states are one form, and this is the seam between them. The field
     * is hidden on the link path deliberately: shown, it would have to be
     * prefilled to be useful, and a prefilled input is the token in the DOM —
     * which "is nowhere in the rendered page" above forbids. Without this, that
     * assertion could be satisfied by a page that simply stopped working.
     */
    stubApi(() => accepted());

    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByLabelText(/new password/i)).toBeVisible());
    expect(screen.queryByLabelText(/reset token/i)).toBeNull();
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

  it("titles the paste state exactly once", async () => {
    search = "";
    stubApi(() => accepted());
    render(<ResetPasswordPage />);

    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeVisible());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
