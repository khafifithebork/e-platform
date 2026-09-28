/**
 * WCAG 2.2 AA, 3.3.8 Accessible Authentication (Minimum) — a password manager
 * must be able to fill these forms.
 *
 * The criterion forbids a cognitive function test in authentication unless an
 * alternative exists. Remembering a password counts as one; the standard escape
 * is that the browser or a password manager can fill it, which requires the
 * fields to be *identifiable* — and `autocomplete` is how a field says what it is.
 *
 * **ADR-030 found this already satisfied and nothing asserted it**, which by
 * ADR-023 §1 means it was not a control. The regression it guards against is not
 * hypothetical: stripping `autocomplete` from login forms is a folk security
 * measure, it looks like hardening, and it breaks the exact mechanism this
 * criterion relies on. Nothing in this repository would have noticed.
 *
 * Rendered rather than grepped. `Field` is what actually puts the attribute on the
 * input, so a source check on the pages would pass if `Field` stopped forwarding
 * the prop.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "@/app/(auth)/forgot-password/page";
import LoginPage from "@/app/(auth)/login/page";
import RegisterPage from "@/app/(auth)/register/page";
import ResetPasswordPage from "@/app/(auth)/reset-password/page";
import VerifyEmailPage from "@/app/(auth)/verify-email/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams("token=t"),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

/**
 * The five pages, and the values each field must claim.
 *
 * Asserting the *value* and not merely its presence, because the value is what
 * does the work: a password manager offers a saved password for
 * `current-password` and a generated one for `new-password`, and getting those
 * two the wrong way round is the failure that looks like it works.
 */
const PAGES = [
  { name: "login", Page: LoginPage, expected: ["email", "current-password"] },
  { name: "register", Page: RegisterPage, expected: ["email", "new-password"] },
  { name: "forgot-password", Page: ForgotPasswordPage, expected: ["email"] },
  { name: "reset-password", Page: ResetPasswordPage, expected: ["new-password"] },
  /**
   * `verify-email` under the mock above, which supplies `token=t` — so the token
   * field is absent and the only input is the resend address. The token field is
   * deliberately `autocomplete="off"`: a single-use token from an email is not
   * something a password manager holds, and offering to fill it would offer the
   * *previous* token.
   */
  { name: "verify-email", Page: VerifyEmailPage, expected: ["email"] },
] as const;

describe("every authentication field is fillable by a password manager", () => {
  for (const { name, Page, expected } of PAGES) {
    it(`${name} declares autocomplete on every input`, () => {
      render(<Page />);

      // `queryAllByRole`, not `getAllByRole`: the latter throws when nothing
      // matches, and `reset-password` has no textbox at all — only a password
      // field. That threw rather than reporting the empty list, which is the
      // failure mode `getAllBy*` is documented to have and easy to forget.
      const inputs = screen.queryAllByRole("textbox").concat(
        // Password inputs have no accessible role, so `getAllByRole` misses them.
        // Querying the DOM directly is the only way to see them, and they are the
        // fields this criterion is most about.
        // Typed selector: `querySelectorAll` is `Element` by default, which does
        // not satisfy `concat` on an `HTMLElement[]`.
        [...document.querySelectorAll<HTMLInputElement>('input[type="password"]')],
      );

      expect(inputs.length).toBe(expected.length);
      expect(inputs.map((i) => i.getAttribute("autocomplete"))).toEqual(expected);
    });
  }

  it("uses new-password where a password is being set, and current-password where it is being given", () => {
    /**
     * The twin, stated as the property rather than per page. If every field were
     * `autocomplete="on"` the tests above would still pass their length check but
     * not this: a manager would offer a saved password on the reset form, where
     * the user needs a *new* one, and would not offer to save the one they just
     * chose.
     */
    const byPage = Object.fromEntries(PAGES.map(({ name, expected }) => [name, expected]));

    expect(byPage.login).toContain("current-password");
    expect(byPage.register).toContain("new-password");
    expect(byPage["reset-password"]).toContain("new-password");
    expect(byPage.login).not.toContain("new-password");
  });

  it("presents no CAPTCHA or puzzle", () => {
    /**
     * The other half of 3.3.8. A CAPTCHA is a cognitive function test with no
     * alternative, and adding one is the other way this criterion gets broken —
     * usually in response to bot traffic, which the backend already handles with
     * `django-axes` lockout and per-IP throttling rather than by asking the user
     * to read distorted letters.
     */
    render(<LoginPage />);

    expect(document.querySelector("iframe")).toBeNull();
    expect(screen.queryByText(/captcha|verify you are human|prove you/i)).toBeNull();
  });
});
