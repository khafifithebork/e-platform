/**
 * The failed-load treatment, and the one structural decision in it.
 *
 * Four surfaces used to end a failed fetch with advice — "Try again in a moment",
 * "Reloading the page usually fixes it" — and nothing to press. The component tests
 * that matter are in those four; this file covers the shared piece, and in
 * particular that the button is **outside** the live region rather than inside it.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoadFailure } from "@/components/ui/LoadFailure";
import { axeViolations } from "@/test/axe";

describe("the message", () => {
  it("announces itself, because the load already failed before anyone looked", async () => {
    render(<LoadFailure onRetry={vi.fn()}>Your courses could not be loaded.</LoadFailure>);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
  });

  it("takes an optional title, for surfaces with no heading of their own", () => {
    render(
      <LoadFailure title="Something went wrong" onRetry={vi.fn()}>
        Details here.
      </LoadFailure>,
    );

    expect(screen.getByText("Something went wrong")).toBeVisible();
  });
});

describe("the retry", () => {
  it("is a button, so a keyboard reaches it", async () => {
    const onRetry = vi.fn();
    render(<LoadFailure onRetry={onRetry}>Failed.</LoadFailure>);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("sits outside the live region, not inside it", () => {
    /**
     * **The structural decision this file exists for.** `Notice` is
     * `role="alert"` with `aria-live="assertive"`, and a live region's job is to
     * announce *text*. A control inside one may have its label read as part of the
     * announcement, and in some screen-reader and browser combinations the whole
     * region is re-announced when the button's own state changes — so pressing
     * "Try again" would re-read the error at somebody.
     */
    render(<LoadFailure onRetry={vi.fn()}>Failed.</LoadFailure>);

    const alert = screen.getByRole("alert");
    const button = screen.getByRole("button", { name: "Try again" });

    expect(alert).not.toContainElement(button);
  });

  it("cannot be pressed twice while a retry is in flight", async () => {
    // A second press starts a second request for the same thing, and the first
    // one's response then arrives after the second's — the out-of-order write the
    // search box aborts requests to avoid.
    const onRetry = vi.fn();
    render(
      <LoadFailure onRetry={onRetry} retrying>
        Failed.
      </LoadFailure>,
    );

    const button = screen.getByRole("button", { name: /trying/i });
    expect(button).toBeDisabled();

    await userEvent.click(button);
    expect(onRetry).not.toHaveBeenCalled();
  });
});

describe("the markup", () => {
  it("has no axe violations", async () => {
    const { container } = render(<LoadFailure onRetry={vi.fn()}>Failed.</LoadFailure>);

    expect(await axeViolations(container)).toEqual([]);
  });
});
