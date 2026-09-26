/**
 * Registration, and the sentence that must stay conditional.
 *
 * The page explains why:
 *
 * > The API answers identically whether the address was free or already taken,
 * > so that someone cannot test a list of addresses against this form. A
 * > cheerful "check your inbox!" is the right words for both outcomes; "we sent
 * > you an email" would be a lie in one of them.
 *
 * The backend went to trouble for that — registering an address that already
 * exists returns the same 201 and silently sends nothing. The whole property
 * then rests on **the frontend not saying more than the backend did**, and
 * until now nothing here asserted it. It is the easiest control in this
 * codebase to break with good intentions: "If your address can be registered, a
 * link is on its way" reads like hedging, and the obvious edit turns the form
 * into a way to check whether a given person has an account.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterPage from "@/app/(auth)/register/page";
import { accepted, refusal, stubApi } from "@/test/api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const EMAIL = "learner@example.test";

async function submit(email = EMAIL) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email/i), email);
  await user.type(screen.getByLabelText(/password/i), "a long enough password");
  await user.click(screen.getByRole("button", { name: /create account/i }));
}

/**
 * Claims the confirmation is not allowed to make.
 *
 * Each of these states as fact something the page cannot know, because the API
 * refused to tell it: that an account now exists, or that an email was sent.
 * Matched against the whole confirmation rather than one element, so moving the
 * wording into a different component does not silently retire the check.
 */
const UNCONDITIONAL_CLAIMS = [
  /\bwe(?:'ve| have)? sent\b/i,
  /\bwe(?:'ve| have)? emailed\b/i,
  /\byour account (?:is|has been) created\b/i,
  /\baccount created\b/i,
  /\bwelcome\b/i,
];

describe("the confirmation after a successful submission", () => {
  it("never states that an account was created or an email sent", async () => {
    stubApi(() => accepted());
    render(<RegisterPage />);

    await submit();

    const confirmation = await screen.findByRole("heading", { level: 1, name: /check your inbox/i });
    const text = confirmation.parentElement?.textContent ?? "";

    for (const claim of UNCONDITIONAL_CLAIMS) {
      expect(text).not.toMatch(claim);
    }

    /**
     * And says so conditionally, rather than by omitting the subject entirely:
     * a confirmation that mentioned neither an account nor an email would pass
     * every assertion above while telling the visitor nothing.
     *
     * Queried element-by-element rather than against `text`, because
     * `textContent` concatenates with no separator — the first attempt asserted
     * `/\bif\b/` over the whole confirmation and failed against entirely
     * correct copy, on `"Almost there" + "If …"` arriving as `"thereIf"` with no
     * word boundary between them. The same trap in the other direction is what
     * `forgot-password/page.test.tsx` fell into.
     */
    expect(within(screen.getByRole("status")).getByText(/^if\b/i)).toBeVisible();
  });

  it("is reading the confirmation and not an empty element", async () => {
    // The twin. `textContent` of a node that failed to render is "", which
    // matches none of the claims above — so the test that matters would pass
    // against a page that showed nothing at all.
    stubApi(() => accepted());
    render(<RegisterPage />);

    await submit();

    await waitFor(() => expect(screen.getByText(EMAIL)).toBeVisible());
    expect(screen.getByRole("status")).toBeVisible();
  });

  it("does not appear when the request failed", async () => {
    /**
     * The state machine, not the wording. `submitted` is set inside the `try`,
     * after the call — a page that set it before, or in the `finally`, would
     * show "Check your inbox" to somebody whose registration was refused, and
     * they would wait for an email that is not coming.
     */
    stubApi(() => refusal(500, "Something went wrong. Please try again."));
    render(<RegisterPage />);

    await submit();

    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(screen.queryByRole("heading", { level: 1, name: /check your inbox/i })).toBeNull();
    expect(screen.getByRole("button", { name: /create account/i })).toBeVisible();
  });
});

describe("what it sends", () => {
  it("posts the address and password the visitor typed, and nothing else", async () => {
    const fetchMock = stubApi(() => accepted());
    render(<RegisterPage />);

    await submit();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const [body] = fetchMock.mock.calls
      .filter(([input]) => String(input).endsWith("/auth/register/"))
      .map(([, init]) => JSON.parse(String(init?.body)));

    expect(body).toEqual({ email: EMAIL, password: "a long enough password" });
  });

  it("shows the API's wording when registration is refused, without inventing a reason", async () => {
    stubApi(() =>
      refusal(400, "Your input was invalid.", {
        password: ["This password is too common."],
      }),
    );
    render(<RegisterPage />);

    await submit();

    await waitFor(() => expect(screen.getByText("This password is too common.")).toBeVisible());
  });
});

describe("the heading outline", () => {
  it("titles the form state exactly once", async () => {
    stubApi(() => accepted());
    render(<RegisterPage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("titles the confirmation state exactly once", async () => {
    // The confirmation is a separate early return, so it has its own `<h1>` and
    // its own chance to grow a second one.
    stubApi(() => accepted());
    render(<RegisterPage />);

    await submit();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
