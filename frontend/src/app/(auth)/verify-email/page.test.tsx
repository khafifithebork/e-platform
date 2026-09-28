/**
 * Redeeming a verification token, and the three properties that are claims the
 * page makes about itself.
 *
 * 1. A token from `?token=` reaches the API and **nowhere else** — not the DOM,
 *    not storage. Mirrors `reset-password/page.test.tsx` deliberately rather than
 *    sharing a helper: two pages carrying the same property independently is
 *    worth more than the duplication costs, because a shared helper is one edit
 *    away from retiring both checks at once.
 * 2. Verification happens on a click and **never on mount**. A verification token
 *    is single-use, so an effect that posted on render would fail on the second
 *    of React's double-invoked development effects, on a refresh, and on a
 *    back-navigation — reporting "not valid" for a token that verified.
 * 3. The resend confirmation holds for three outcomes the API refuses to
 *    distinguish: unknown address, already-verified address, genuine resend.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VerifyEmailPage from "@/app/(auth)/verify-email/page";
import { accepted, refusal, stubApi } from "@/test/api";
import { axeViolations } from "@/test/axe";

/** Long and distinctive, so a leak into the markup is findable. */
const TOKEN = "dmVyaWZpY2F0aW9uLXRva2VuLWZpbmRhYmxlLTQy";

let search = "";
let suspend = false;
const never = new Promise<never>(() => {});

vi.mock("next/navigation", () => ({
  useSearchParams: () => {
    // Throwing a promise is how a component suspends, and the only way to reach
    // the fallback from here: with `useSearchParams` mocked, nothing else in this
    // subtree ever suspends.
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

const verifyCalls = (fetchMock: ReturnType<typeof stubApi>) =>
  fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/auth/verify-email/"));

async function clickVerify() {
  await userEvent.setup().click(screen.getByRole("button", { name: /verify my address/i }));
}

describe("a token in the URL", () => {
  it("is nowhere in the rendered page", async () => {
    const { container } = render(<VerifyEmailPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /verify my address/i })).toBeVisible(),
    );

    // `innerHTML`, not `textContent`: the failure worth catching is a `value=`,
    // `href=` or `data-` attribute carrying it, which no visible-text assertion
    // would see.
    expect(container.innerHTML).not.toContain(TOKEN);
  });

  it("is not in storage either", async () => {
    render(<VerifyEmailPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /verify my address/i })).toBeVisible(),
    );

    expect(JSON.stringify({ ...localStorage })).not.toContain(TOKEN);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(TOKEN);
  });

  it("does reach the API, which is the only place it should go", async () => {
    // The twin for both tests above: a page that dropped the token entirely would
    // satisfy them and then fail every real verification.
    const fetchMock = stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await clickVerify();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(verifyCalls(fetchMock).map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      { token: TOKEN },
    ]);
  });

  it("is not posted until the button is pressed", async () => {
    /**
     * Property 2, and the reason this page has a button at all rather than an
     * effect. Single-use means a second POST fails, so anything that verifies on
     * render turns a working token into "not valid" on the next mount.
     */
    const fetchMock = stubApi(() => accepted());

    render(<VerifyEmailPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /verify my address/i })).toBeVisible(),
    );
    expect(verifyCalls(fetchMock)).toHaveLength(0);

    await clickVerify();
    await waitFor(() => expect(verifyCalls(fetchMock)).toHaveLength(1));
  });

  it("does not offer the paste field, because prefilling it would render the token", async () => {
    // The seam between the two states. Shown on this path the field would have to
    // be prefilled to be useful, and a prefilled input is the token in the DOM.
    stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /verify my address/i })).toBeVisible(),
    );
    expect(screen.queryByLabelText(/verification token/i)).toBeNull();
  });
});

describe("a visit with no token in the URL", () => {
  beforeEach(() => {
    search = "";
  });

  it("offers a field to paste it into, because that is what the email sends", async () => {
    /**
     * `email/verification/body.txt` sends the token as bare text with no URL —
     * there is no configured site URL to build one from — so this is the path
     * every real verification takes today. Until this page existed there was no
     * path at all: the endpoint had no caller.
     */
    stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await waitFor(() => expect(screen.getByLabelText(/verification token/i)).toBeVisible());
  });

  it("sends the pasted token", async () => {
    const fetchMock = stubApi(() => accepted());
    const user = userEvent.setup();
    render(<VerifyEmailPage />);

    await waitFor(() => expect(screen.getByLabelText(/verification token/i)).toBeVisible());
    await user.type(screen.getByLabelText(/verification token/i), TOKEN);
    await clickVerify();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(verifyCalls(fetchMock).map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      { token: TOKEN },
    ]);
  });

  it("does not post an empty token when the field is left blank", async () => {
    // An empty token cannot succeed: `verify_email` short-circuits it so a digest
    // of the empty string cannot match a stored row. Posting one spends a
    // rate-limit slot on a certain failure.
    const fetchMock = stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await waitFor(() => expect(screen.getByLabelText(/verification token/i)).toBeVisible());
    await clickVerify();

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/paste the token/i),
    );
    expect(verifyCalls(fetchMock)).toHaveLength(0);
  });
});

describe("when the token does not work", () => {
  it("shows what the API said and keeps the form", async () => {
    // The API deliberately does not distinguish unknown, expired and already-used,
    // so the page has one message to show and must not invent a reason.
    stubApi(() => refusal(400, "That verification link is not valid."));
    render(<VerifyEmailPage />);

    await clickVerify();

    await waitFor(() =>
      expect(screen.getByText("That verification link is not valid.")).toBeVisible(),
    );
    expect(screen.queryByRole("heading", { level: 1, name: /verified/i })).toBeNull();
    expect(screen.getByRole("button", { name: /verify my address/i })).toBeVisible();
  });

  it("is not a dead end", async () => {
    // The whole reason the resend sits on this page: a failed verification is
    // where somebody needs a fresh token, and there is nowhere else to get one.
    stubApi(() => refusal(400, "That verification link is not valid."));
    render(<VerifyEmailPage />);

    await clickVerify();

    await waitFor(() =>
      expect(screen.getByText("That verification link is not valid.")).toBeVisible(),
    );
    expect(screen.getByRole("button", { name: /send a new token/i })).toBeVisible();
  });
});

describe("the resend confirmation", () => {
  const RESEND_CLAIMS = [
    /\bwe(?:'ve| have)? sent\b/i,
    /\bwe(?:'ve| have)? emailed\b/i,
    /\byour account\b/i,
  ];

  async function resend(email = "learner@example.test") {
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/^email$/i), email);
    await user.click(screen.getByRole("button", { name: /send a new token/i }));
  }

  it("never confirms that the address has an unverified account", async () => {
    stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /send a new token/i })).toBeVisible(),
    );
    await resend();

    const notice = await screen.findByRole("status");
    for (const claim of RESEND_CLAIMS) {
      expect(notice.textContent ?? "").not.toMatch(claim);
    }

    /**
     * And says so conditionally rather than by omitting the subject — a notice
     * mentioning neither an account nor an email would pass every assertion above
     * while telling the visitor nothing.
     *
     * Queried element-by-element, not against `textContent`: the title "Sent, if
     * we could" and the body's "If" concatenate as `"couldIf"` with no word
     * boundary, which is exactly how the same assertion on `forgot-password`
     * passed for the wrong reason for a while.
     */
    expect(within(notice).getByText(/^if\b/i)).toBeVisible();
  });

  it("answers the same way for an address that cannot possibly have an account", async () => {
    /**
     * The assertion that makes this a control rather than a copy test. The API
     * returns the same 202 for all three outcomes, so the page has nothing to
     * branch on — and the rendered confirmation must come out byte-identical for
     * two different addresses apart from the address itself.
     */
    stubApi(() => accepted());

    const first = render(<VerifyEmailPage />);
    await resend("member@example.test");
    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const known = first.container.innerHTML.replace("member@example.test", "ADDRESS");
    first.unmount();

    const second = render(<VerifyEmailPage />);
    await resend("nobody@example.test");
    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const unknown = second.container.innerHTML.replace("nobody@example.test", "ADDRESS");

    expect(unknown).toBe(known);
  });

  it("posts the address to the resend endpoint", async () => {
    const fetchMock = stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await resend();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const bodies = fetchMock.mock.calls
      .filter(([input]) => String(input).endsWith("/auth/resend-verification/"))
      .map(([, init]) => JSON.parse(String(init?.body)));

    expect(bodies).toEqual([{ email: "learner@example.test" }]);
  });

  it("does not appear when the request failed", async () => {
    stubApi(() => refusal(429, "Too many requests. Try again later."));
    render(<VerifyEmailPage />);

    await resend();

    await waitFor(() =>
      expect(screen.getByText("Too many requests. Try again later.")).toBeVisible(),
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("after a successful verification", () => {
  it("sends them to sign in", async () => {
    stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await clickVerify();

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/verified/i),
    );
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });
});

describe("the markup", () => {
  /**
   * axe over the states this page adds, because two forms on one page is where
   * the markup faults live: a duplicated id between the two, a heading level that
   * skips, an `aria-describedby` pointing at a field error in the other form.
   * `src/test/axe.ts` records which rule families cannot run in jsdom and what
   * covers them instead.
   */
  it("has no violations in the paste state, with both forms on screen", async () => {
    search = "";
    stubApi(() => accepted());

    const { container } = render(<VerifyEmailPage />);

    await waitFor(() => expect(screen.getByLabelText(/verification token/i)).toBeVisible());
    expect(await axeViolations(container)).toEqual([]);
  });

  it("has no violations once a field error is showing", async () => {
    // The state that carries the ARIA: `aria-invalid` and an `aria-describedby`
    // pointing at the error, on one of two forms.
    search = "";
    stubApi(() => accepted());

    const { container } = render(<VerifyEmailPage />);

    await waitFor(() => expect(screen.getByLabelText(/verification token/i)).toBeVisible());
    await clickVerify();

    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(await axeViolations(container)).toEqual([]);
  });

  it("has no violations in the verified state", async () => {
    stubApi(() => accepted());

    const { container } = render(<VerifyEmailPage />);
    await clickVerify();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("the prerendered page", () => {
  it("carries a heading while the client half is still loading", async () => {
    /**
     * `useSearchParams` forces the form onto the client, so the whole static
     * document for this route is the Suspense fallback. A fallback without an
     * `<h1>` means the served HTML has no title in its heading outline, which is
     * how a screen-reader user establishes where they are before hydration.
     */
    suspend = true;

    render(<VerifyEmailPage />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        /verify your email address/i,
      ),
    );
  });
});

describe("the heading outline", () => {
  it("titles each state exactly once", async () => {
    stubApi(() => accepted());
    render(<VerifyEmailPage />);

    await waitFor(() => expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1));

    await clickVerify();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/verified/i),
    );
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
