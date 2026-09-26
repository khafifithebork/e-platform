/**
 * The sign-in form, and the control it carries in a comment.
 *
 * The page says this about its error handling:
 *
 * > The API answers identically for a wrong password, an unknown address and a
 * > locked account. Echoing its message verbatim is what keeps that true —
 * > inventing a friendlier one here would leak the distinction the backend went
 * > to trouble to hide.
 *
 * That is correct, it is the reason the backend's login view is written the way
 * it is, and until now **nothing asserted it**. ADR-023 §1: a decision recorded
 * in a comment is not a control until something fails when it is broken. The
 * regression it guards against is not exotic — it is somebody deciding that
 * "Unable to sign in with the credentials provided" is unhelpful and replacing
 * it with "No account with that email", which turns the form into an account
 * enumeration oracle without changing a line of backend code.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/(auth)/login/page";
import { accepted, refusal, stubApi } from "@/test/api";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  push.mockReset();
});

async function signIn(email = "learner@example.test", password = "correct horse") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email/i), email);
  await user.type(screen.getByLabelText(/password/i), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("what the page says when sign-in is refused", () => {
  it("shows the API's wording, exactly as the API worded it", async () => {
    stubApi(() => refusal(400, "Unable to sign in with the credentials provided."));
    render(<LoginPage />);

    await signIn();

    await waitFor(() =>
      expect(
        screen.getByText("Unable to sign in with the credentials provided."),
      ).toBeVisible(),
    );
  });

  it("shows a different refusal too, so the message is echoed and not hardcoded", async () => {
    /**
     * **The twin, and the one that does the work.** A page that ignored the
     * response and printed one fixed sentence would pass the test above. This
     * fails against that page, because the sentence it asserts is one no
     * frontend would have chosen for itself — it is the backend's wording for
     * a locked account, which is deliberately the same shape as the wrong
     * password message.
     */
    stubApi(() => refusal(429, "Too many attempts. Try again in a few minutes."));
    render(<LoginPage />);

    await signIn();

    await waitFor(() =>
      expect(screen.getByText("Too many attempts. Try again in a few minutes.")).toBeVisible(),
    );
    expect(screen.queryByText(/credentials provided/i)).toBeNull();
  });

  it("does not send the visitor anywhere when sign-in failed", async () => {
    // The quiet version of this bug: a form that navigates on submit rather
    // than on success shows the landing page to somebody who is still signed
    // out, and they discover it one click later.
    stubApi(() => refusal(400, "Unable to sign in with the credentials provided."));
    render(<LoginPage />);

    await signIn();

    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(push).not.toHaveBeenCalled();
  });

  it("distinguishes a server it could not reach from a server that said no", async () => {
    /**
     * The non-`ApiError` branch. `fetch` rejects on a dropped connection rather
     * than resolving with a status, so this path never produces a problem
     * document and the page has to supply its own sentence. That is the one
     * message it is allowed to invent, because there is no answer to echo.
     */
    stubApi(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<LoginPage />);

    await signIn();

    await waitFor(() => expect(screen.getByText(/could not reach the server/i)).toBeVisible());
  });

  it("puts field errors on the field they belong to", async () => {
    stubApi(() =>
      refusal(400, "Your input was invalid.", { email: ["Enter a valid email address."] }),
    );
    render(<LoginPage />);

    await signIn("not-an-address", "correct horse");

    await waitFor(() => expect(screen.getByText("Enter a valid email address.")).toBeVisible());
    // `Field` links the message with `aria-describedby` and marks the input
    // invalid; a message rendered loose in the form reaches a sighted user and
    // nobody else.
    expect(screen.getByLabelText(/email/i)).toHaveAttribute("aria-invalid", "true");
  });
});

describe("what the page does when sign-in succeeds", () => {
  it("posts the credentials and sends the visitor to the catalogue", async () => {
    stubApi(() => accepted());
    render(<LoginPage />);

    await signIn();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("never puts anything auth-related in storage", async () => {
    /**
     * Invariant 9, at the one place in the app where a session is created.
     * `AuthMenu` carries the same check for the read side; this is the write
     * side, and a form is where somebody would cache the email "to prefill it
     * next time".
     */
    stubApi(() => accepted());
    render(<LoginPage />);

    await signIn();

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

describe("the heading outline", () => {
  it("titles the page exactly once", async () => {
    // Every state of every auth page gets this check. A second `<h1>` appearing
    // from a copy-paste is invisible on screen and turns the heading outline —
    // how a screen-reader user establishes where they are — into a guess.
    stubApi(() => accepted());
    render(<LoginPage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
