/**
 * The account page's details, and the one property that matters most.
 *
 * **Everything shown here is the server's answer, not a local computation** — the
 * access state above all. Invariant 3: one resolver, and the frontend never
 * re-derives its rules. The tests that carry weight are the ones that would fail if
 * this component started deciding anything: the label comes from the payload, the
 * destination comes from the payload's `cta`, and two different payloads produce two
 * different renderings.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountDetails } from "@/components/account/AccountDetails";
import { axeViolations } from "@/test/axe";
import { json, refusal, stubApi } from "@/test/api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** A signed-in learner, shaped like `/auth/me/`. */
function me(overrides: Record<string, unknown> = {}) {
  return {
    id: "u1",
    email: "learner@example.test",
    role: "STUDENT",
    is_email_verified: true,
    profile: { display_name: "" },
    access: {
      allowed: true,
      reason: "SUBSCRIPTION_ACTIVE",
      cta: null,
      label: "Active subscription",
    },
    ...overrides,
  };
}

describe("your details", () => {
  it("preserves long account details and the server access label verbatim", async () => {
    const email = `${"long-address".repeat(15)}@example.test`;
    const label = "Server-supplied access label ".repeat(12);
    stubApi(() => json(me({ email, profile: { display_name: "متعلم".repeat(50) }, access: { allowed: false, reason: "SUBSCRIPTION_EXPIRED", cta: "subscribe", label } })));
    render(<AccountDetails />);
    expect(await screen.findByText(email)).toBeVisible();
    expect(screen.getByText(label.trim())).toBeVisible();
    expect(screen.getByRole("link", { name: "See what a subscription covers" })).toHaveAttribute("href", "/pricing");
  });

  it("shows the address the session belongs to", async () => {
    stubApi(() => json(me()));
    render(<AccountDetails />);

    expect(await screen.findByText("learner@example.test")).toBeVisible();
  });

  it("offers verification when the address is not confirmed, and not when it is", async () => {
    /**
     * Both directions in one test, because the interesting failure is a link that
     * is always there — which would tell a verified learner to verify again, and
     * send them to a page whose only outcome is an error.
     *
     * The link exists at all because batch one built `/verify-email` on
     * 2026-09-28. Before that this state could be reported and not acted on.
     */
    stubApi(() => json(me({ is_email_verified: false })));
    const unverified = render(<AccountDetails />);

    const link = await screen.findByRole("link", { name: /confirm it now/i });
    expect(link).toHaveAttribute("href", "/verify-email");
    unverified.unmount();

    stubApi(() => json(me({ is_email_verified: true })));
    render(<AccountDetails />);

    await waitFor(() => expect(screen.getByText("learner@example.test")).toBeVisible());
    expect(screen.queryByRole("link", { name: /confirm it now/i })).toBeNull();
  });

  it("omits the display name when the API sends an empty one", async () => {
    // The API documents it as empty when unset, and an empty row reads as a broken
    // field rather than an unused one. There is no way to set it — no endpoint.
    stubApi(() => json(me({ profile: { display_name: "" } })));
    render(<AccountDetails />);

    await waitFor(() => expect(screen.getByText("learner@example.test")).toBeVisible());
    expect(screen.queryByText(/display name/i)).toBeNull();
  });

  it("shows the display name when there is one", async () => {
    // The twin. A component that never rendered the row would pass the test above.
    stubApi(() => json(me({ profile: { display_name: "Amina" } })));
    render(<AccountDetails />);

    expect(await screen.findByText("Amina")).toBeVisible();
    expect(screen.getByText(/display name/i)).toBeVisible();
  });

  it("names a role only when it is not the default one", async () => {
    // "Student" tells a learner nothing. An instructor seeing their role is being
    // told which surfaces apply to them.
    stubApi(() => json(me({ role: "INSTRUCTOR" })));
    const instructor = render(<AccountDetails />);

    expect(await screen.findByText("INSTRUCTOR")).toBeVisible();
    instructor.unmount();

    stubApi(() => json(me({ role: "STUDENT" })));
    render(<AccountDetails />);

    await waitFor(() => expect(screen.getByText("learner@example.test")).toBeVisible());
    expect(screen.queryByText(/^role$/i)).toBeNull();
  });
});

describe("course access", () => {
  it("shows the server's label rather than a locally chosen sentence", async () => {
    /**
     * **The assertion this component exists to satisfy.** `label` was added to
     * `AccessSerializer` on 2026-09-29 precisely so the frontend would not keep its
     * own table of twelve reason strings — and `denial.ts` records what such a
     * table costs, having branched for nine milestones on two reasons the server
     * has never sent.
     *
     * The label here is deliberately not one the resolver would really pair with
     * `NO_SUBSCRIPTION`: if this component were mapping the *reason* to words of
     * its own, it would print something else and this would fail.
     */
    stubApi(() =>
      json(
        me({
          access: {
            allowed: false,
            reason: "NO_SUBSCRIPTION",
            cta: "subscribe",
            label: "A label only the server could have sent",
          },
        }),
      ),
    );

    render(<AccountDetails />);

    expect(await screen.findByText("A label only the server could have sent")).toBeVisible();
  });

  it("states whether access is allowed, from `allowed` and not from the reason", async () => {
    /**
     * **The first version of this test could not fail, and provoking found it.**
     *
     * It used `allowed: true` with `SUBSCRIPTION_ACTIVE` and `allowed: false` with
     * `SUBSCRIPTION_EXPIRED` — fixtures where reading `allowed` and deriving it from
     * `reason === "SUBSCRIPTION_ACTIVE"` give the same answer. Replacing the read
     * with exactly that derivation left the test green, while the test's own name
     * claimed to rule it out.
     *
     * So the fixtures now **disagree**. `GRACE_PERIOD` is a grant — the payment
     * failed and the person is still inside the window — and `TRIAL` is a grant too.
     * A component deriving access from the reason denies both, which is a real bug:
     * it would tell a paying customer mid-grace and every trial user that they have
     * no access. Eight of the fourteen reasons are grants; keying on one of them is
     * wrong for seven.
     */
    stubApi(() =>
      json(
        me({
          access: {
            allowed: true,
            reason: "GRACE_PERIOD",
            cta: null,
            label: "Payment failed, within grace period",
          },
        }),
      ),
    );
    const inGrace = render(<AccountDetails />);

    expect(await screen.findByText(/you have access to every published course/i)).toBeVisible();
    inGrace.unmount();

    stubApi(() =>
      json(
        me({ access: { allowed: true, reason: "TRIAL", cta: null, label: "Trial in progress" } }),
      ),
    );
    const onTrial = render(<AccountDetails />);

    expect(await screen.findByText(/you have access to every published course/i)).toBeVisible();
    onTrial.unmount();

    stubApi(() =>
      json(
        me({
          access: {
            allowed: false,
            reason: "SUBSCRIPTION_EXPIRED",
            cta: "subscribe",
            label: "Subscription ended",
          },
        }),
      ),
    );
    render(<AccountDetails />);

    expect(await screen.findByText(/do not currently have access/i)).toBeVisible();
  });

  it("follows the server's cta to a destination, and offers none when there is no cta", async () => {
    stubApi(() =>
      json(
        me({
          access: { allowed: false, reason: "LOGIN_REQUIRED", cta: "login", label: "Not signed in" },
        }),
      ),
    );
    const needsLogin = render(<AccountDetails />);

    expect(await screen.findByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
    needsLogin.unmount();

    // A grant sends no cta, and there is nothing to offer.
    stubApi(() => json(me()));
    render(<AccountDetails />);

    await waitFor(() => expect(screen.getByText("Active subscription")).toBeVisible());
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("sends a failed payment to pricing, because there is no billing portal", async () => {
    /**
     * `update_payment` is the one CTA with nowhere real to go: §11 #1 is unresolved,
     * so there is no provider and no card to update. Pointing at `/pricing`, which
     * says pricing is not announced, is the honest placeholder — and pinning it here
     * means M8 has to change this deliberately rather than discover it.
     */
    stubApi(() =>
      json(
        me({
          access: {
            allowed: false,
            reason: "GRACE_PERIOD_ENDED",
            cta: "update_payment",
            label: "Payment failed and grace period ended",
          },
        }),
      ),
    );

    render(<AccountDetails />);

    expect(await screen.findByRole("link")).toHaveAttribute("href", "/pricing");
  });
});

describe("when there is no session", () => {
  it("offers a way in rather than reporting an error", async () => {
    /**
     * A 403 from `/auth/me/` is the answer to "who am I", not a failure. Treating it
     * as one would show somebody an error for a request they did not make.
     *
     * **The type, not the status**, and getting this wrong is what the first run of
     * this test caught — in the fixture rather than the component. Django answers 403
     * for both "not signed in" and "not allowed" because `SessionAuthentication`
     * sends no `WWW-Authenticate` header, so `isNotAuthenticated` reads
     * `problem.type` (ADR-004). A 403 with a different type is a permission refusal
     * and must not render as "sign in".
     */
    stubApi(() =>
      json(
        {
          type: "/problems/not-authenticated",
          title: "Not authenticated",
          status: 403,
          detail: "Authentication credentials were not provided.",
          errors: null,
        },
        403,
      ),
    );
    render(<AccountDetails />);

    expect(await screen.findByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does report an error when the API actually failed", async () => {
    // The twin, and the distinction the component is built around: a 500 is not a
    // signed-out visitor, and telling somebody to sign in would be wrong advice.
    stubApi(() => refusal(500, "Something went wrong."));
    render(<AccountDetails />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
  });

  it("offers a retry that re-requests, rather than telling somebody to reload", async () => {
    /**
     * This used to say "Reloading the page usually fixes it". Reloading would also
     * discard anything typed into the password form further down the page — so the
     * advice was not only unhelpful, it was destructive to follow.
     */
    const fetchMock = stubApi(() => refusal(500, "Something went wrong."));

    render(<AccountDetails />);
    await screen.findByRole("alert");
    const before = fetchMock.mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
  });

  it("recovers when the retry succeeds", async () => {
    // The half that proves the retry is a real reload of the data and not a button
    // that clears the message.
    let failing = true;
    stubApi(() => (failing ? refusal(500, "Something went wrong.") : json(me())));

    render(<AccountDetails />);
    await screen.findByRole("alert");

    failing = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("learner@example.test")).toBeVisible();
  });

  it("reports an error for a 403 that is a permission refusal, not a missing session", async () => {
    /**
     * The third case, and the one the status code cannot distinguish. A 403 whose
     * type is *not* `/problems/not-authenticated` means signed in and not allowed —
     * telling that person to sign in would send them to a page they do not need and
     * leave them no wiser.
     */
    stubApi(() => refusal(403, "You do not have permission to perform this action."));
    render(<AccountDetails />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
  });
});

describe("the markup", () => {
  it("has no axe violations in the states that carry structure", async () => {
    // A description list and two labelled sections — the parts a heading level or a
    // `<dt>`/`<dd>` pairing can get wrong.
    stubApi(() => json(me({ is_email_verified: false, profile: { display_name: "Amina" } })));

    const { container } = render(<AccountDetails />);

    await waitFor(() => expect(screen.getByText("Amina")).toBeVisible());
    expect(await axeViolations(container)).toEqual([]);
  });
});
