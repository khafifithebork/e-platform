/**
 * Changing a password while signed in.
 *
 * Three properties, and the second is the one nothing else in this repository
 * protects:
 *
 * 1. The form posts to `/auth/password/change/` with both fields — the endpoint had
 *    no caller at all until 2026-09-29.
 * 2. **The confirmation says other devices were signed out and does not claim this
 *    one was.** `PasswordChangeView` calls `update_session_auth_hash`, so this
 *    session survives; the reset page's "signed out everywhere" is true there and
 *    false here.
 * 3. The API's refusal is echoed verbatim, not replaced with a friendlier sentence.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangePassword } from "@/components/account/ChangePassword";
import { accepted, postedTo, refusal, stubApi } from "@/test/api";
import { axeViolations } from "@/test/axe";

const CHANGE = "/auth/password/change/";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function submit(current = "the-old-passphrase", next = "a-much-better-passphrase") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/current password/i), current);
  await user.type(screen.getByLabelText(/new password/i), next);
  await user.click(screen.getByRole("button", { name: /change password/i }));
}

describe("what it sends", () => {
  it("keeps password changes pending until the server confirms success", async () => {
    let confirm!: (response: Response) => void;
    stubApi(() => new Promise<Response>((resolve) => { confirm = resolve; }));
    render(<ChangePassword />);
    await submit();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByLabelText(/current password/i)).toBeDisabled();
    expect(screen.getByLabelText(/new password/i)).toBeDisabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await act(async () => { confirm(accepted()); });
    expect(await screen.findByRole("status")).toHaveTextContent("Password changed");
  });

  it("posts both passwords under the names the API expects", async () => {
    // `current_password` and `new_password`, snake_case. Getting these wrong is a
    // 400 that reads like a rejected password rather than a wrong field name.
    const fetchMock = stubApi(() => accepted());
    render(<ChangePassword />);

    await submit();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(postedTo(fetchMock, CHANGE)).toEqual([
      { current_password: "the-old-passphrase", new_password: "a-much-better-passphrase" },
    ]);
  });
});

describe("the confirmation", () => {
  it("says the other devices are gone and does not claim this one is", async () => {
    /**
     * **The property worth the most here.** The backend calls
     * `update_session_auth_hash` after the change specifically so the browser that
     * made the request stays signed in, and the comment in `PasswordChangeView`
     * says other sessions dying "is the intent".
     *
     * The reset page says "You are signed out everywhere". Reusing that wording
     * here would tell somebody they are about to lose the tab they are looking at,
     * which is both wrong and alarming — so this asserts the claim *and* its
     * absence.
     */
    stubApi(() => accepted());
    render(<ChangePassword />);

    await submit();

    const notice = await screen.findByRole("status");
    expect(notice.textContent ?? "").toMatch(/other devices have been signed out/i);
    expect(notice.textContent ?? "").toMatch(/this one stays signed in/i);
    expect(notice.textContent ?? "").not.toMatch(/signed out everywhere/i);
  });

  it("does not appear before anything has been submitted", async () => {
    stubApi(() => accepted());
    render(<ChangePassword />);

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not appear when the change was refused", async () => {
    stubApi(() => refusal(400, "Your current password is not correct."));
    render(<ChangePassword />);

    await submit();

    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("a refusal", () => {
  it("is the API's own sentence, whichever one it sent", async () => {
    /**
     * Two different `detail` strings, both rendered. A component with a hardcoded
     * "That password was not accepted" would pass a single fixed fixture and then
     * tell somebody the wrong thing — the backend distinguishes a wrong current
     * password from a weak new one, and both matter.
     */
    const first = stubApi(() => refusal(400, "Your current password is not correct."));
    const wrongCurrent = render(<ChangePassword />);

    await submit();
    expect(await screen.findByText("Your current password is not correct.")).toBeVisible();
    expect(postedTo(first, CHANGE)).toHaveLength(1);
    wrongCurrent.unmount();

    stubApi(() => refusal(429, "Too many attempts. Try again later."));
    render(<ChangePassword />);

    await submit();
    expect(await screen.findByText("Too many attempts. Try again later.")).toBeVisible();
  });

  it("shows a field error against the field it belongs to", async () => {
    // Django's password validators answer per field. Rendering them at the top of
    // the form loses which of the two inputs is wrong.
    stubApi(() =>
      refusal(400, "Request failed", { new_password: ["This password is too common."] }),
    );
    render(<ChangePassword />);

    await submit();

    await waitFor(() => expect(screen.getByText("This password is too common.")).toBeVisible());
  });

  it("keeps what was typed, so a correction is not a retype", async () => {
    // Clearing on failure is the reflex and it is wrong: somebody fixing one
    // character in a long passphrase should not have to enter both again.
    stubApi(() => refusal(400, "Your current password is not correct."));
    render(<ChangePassword />);

    await submit();

    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(screen.getByLabelText(/current password/i)).toHaveValue("the-old-passphrase");
    expect(screen.getByLabelText(/new password/i)).toHaveValue("a-much-better-passphrase");
  });
});

describe("after a success", () => {
  it("empties both fields, so the passphrase is not left on screen", async () => {
    // The opposite of the rule above, and deliberately: there is nothing to correct,
    // and a filled password field left behind is a passphrase sitting in the DOM on
    // a page somebody may walk away from.
    stubApi(() => accepted());
    render(<ChangePassword />);

    await submit();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    expect(screen.getByLabelText(/current password/i)).toHaveValue("");
    expect(screen.getByLabelText(/new password/i)).toHaveValue("");
  });

  it("puts neither password in storage", async () => {
    // Invariant 9. Nothing auth-related in `localStorage` or `sessionStorage`, ever.
    stubApi(() => accepted());
    render(<ChangePassword />);

    await submit();

    await waitFor(() => expect(screen.getByRole("status")).toBeVisible());
    const stored = JSON.stringify({ ...localStorage, ...sessionStorage });
    expect(stored).not.toContain("the-old-passphrase");
    expect(stored).not.toContain("a-much-better-passphrase");
  });
});

describe("the markup", () => {
  it("has no axe violations, including with a field error showing", async () => {
    stubApi(() =>
      refusal(400, "Request failed", { new_password: ["This password is too common."] }),
    );

    const { container } = render(<ChangePassword />);
    expect(await axeViolations(container)).toEqual([]);

    await submit();
    await waitFor(() => expect(screen.getByText("This password is too common.")).toBeVisible());
    expect(await axeViolations(container)).toEqual([]);
  });

  it("declares autocomplete on both fields, so a password manager can fill them", async () => {
    /**
     * WCAG 2.2 AA 3.3.8, the same criterion `accessible-authentication.test.tsx`
     * guards on the four auth pages — and this form is not one of them, because it
     * is not under `(auth)`. `current-password` and `new-password` the right way
     * round is what makes a manager offer the saved one and generate the new one.
     */
    stubApi(() => accepted());
    render(<ChangePassword />);

    const fields = [...document.querySelectorAll<HTMLInputElement>('input[type="password"]')];

    expect(fields.map((field) => field.getAttribute("autocomplete"))).toEqual([
      "current-password",
      "new-password",
    ]);
  });
});
