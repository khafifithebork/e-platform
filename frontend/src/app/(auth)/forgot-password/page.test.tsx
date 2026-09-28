/**
 * Requesting a reset link — the same control as registration, one form over.
 *
 * "Same reasoning as registration: the wording holds whether or not an account
 * exists, because the API refuses to say which." A reset form is the more
 * attractive oracle of the two: it takes an address, needs no password, and
 * ordinarily answers "we've emailed you" — so the version of this page somebody
 * would write without thinking about it confirms membership to anyone who asks.
 *
 * The assertions mirror `register/page.test.tsx` deliberately rather than
 * sharing a helper. Two pages carrying the same property independently is worth
 * more here than the duplication costs: a shared helper is one edit away from
 * retiring both checks at once.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "@/app/(auth)/forgot-password/page";
import { accepted, refusal, stubApi } from "@/test/api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const EMAIL = "learner@example.test";

async function submit(email = EMAIL) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email/i), email);
  await user.click(screen.getByRole("button", { name: /send reset token/i }));
}

const UNCONDITIONAL_CLAIMS = [
  /\bwe(?:'ve| have)? sent\b/i,
  /\bwe(?:'ve| have)? emailed\b/i,
  /\bcheck the inbox for your account\b/i,
  /\byour account\b/i,
];

describe("the confirmation after a successful request", () => {
  it("never confirms that the address has an account", async () => {
    stubApi(() => accepted());
    render(<ForgotPasswordPage />);

    await submit();

    const heading = await screen.findByRole("heading", { level: 1, name: /check your inbox/i });
    const text = heading.parentElement?.textContent ?? "";

    for (const claim of UNCONDITIONAL_CLAIMS) {
      expect(text).not.toMatch(claim);
    }

    /**
     * **This line passed for the wrong reason and is worth the note.**
     *
     * It was `expect(text).toMatch(/\bif\b/i)` over the whole confirmation, and
     * it was green — matching not the conditional sentence it was written for
     * but the word "if" inside the notice's badge title, *"Sent, if we could"*.
     * The body's own "If" is glued to the title by `textContent`
     * concatenation — `"couldIf"` — so it has no word boundary and never
     * matched. Rewording that title to anything else would have turned a
     * passing test red while the property it checks was untouched, and the same
     * concatenation made registration's copy of this assertion fail against
     * correct code.
     *
     * Asserting on the element whose text actually begins with the condition is
     * both fixes at once.
     */
    expect(within(screen.getByRole("status")).getByText(/^if\b/i)).toBeVisible();
  });

  it("is reading the confirmation and not an empty element", async () => {
    // The twin, for the same reason as registration's: "" matches none of the
    // claims above.
    stubApi(() => accepted());
    render(<ForgotPasswordPage />);

    await submit();

    await waitFor(() => expect(screen.getByText(EMAIL)).toBeVisible());
    expect(screen.getByRole("status")).toBeVisible();
  });

  it("answers the same way for an address that cannot possibly have an account", async () => {
    /**
     * **The assertion that makes this a control rather than a copy test.**
     *
     * The API returns the same 201 either way, so the page has nothing to
     * branch on — and that is precisely the property worth pinning: the
     * rendered confirmation must be byte-identical for two different addresses
     * apart from the address itself. A page that grew a branch here, for any
     * reason, fails this.
     */
    stubApi(() => accepted());

    const first = render(<ForgotPasswordPage />);
    await submit("member@example.test");
    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const known = first.container.innerHTML.replace("member@example.test", "ADDRESS");
    first.unmount();

    const second = render(<ForgotPasswordPage />);
    await submit("nobody@example.test");
    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const unknown = second.container.innerHTML.replace("nobody@example.test", "ADDRESS");

    expect(unknown).toBe(known);
  });

  it("says where the token goes", async () => {
    /**
     * Added 2026-09-28 with the fix for the token that could not be redeemed.
     *
     * The email sends a bare token, not a link, so the confirmation is the only
     * place that can tell someone where to put it. Before this, the page said a
     * "reset link" was coming and offered "Back to sign in" — pointing at the one
     * page the token is no use on.
     */
    stubApi(() => accepted());
    render(<ForgotPasswordPage />);

    await submit();

    const link = await screen.findByRole("link", { name: /set a new password/i });
    expect(link).toHaveAttribute("href", "/reset-password");
  });

  it("does not appear when the request failed", async () => {
    stubApi(() => refusal(429, "Too many requests. Try again later."));
    render(<ForgotPasswordPage />);

    await submit();

    await waitFor(() => expect(screen.getByText("Too many requests. Try again later.")).toBeVisible());
    expect(screen.queryByRole("heading", { level: 1, name: /check your inbox/i })).toBeNull();
  });
});

describe("what it sends", () => {
  it("posts the address to the reset endpoint", async () => {
    const fetchMock = stubApi(() => accepted());
    render(<ForgotPasswordPage />);

    await submit();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const [body] = fetchMock.mock.calls
      .filter(([input]) => String(input).endsWith("/auth/password/reset/"))
      .map(([, init]) => JSON.parse(String(init?.body)));

    expect(body).toEqual({ email: EMAIL });
  });
});

describe("the heading outline", () => {
  it("titles each state exactly once", async () => {
    stubApi(() => accepted());
    render(<ForgotPasswordPage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);

    await submit();
    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
