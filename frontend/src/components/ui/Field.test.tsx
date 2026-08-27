/**
 * `Field` and `Notice`, tested through the accessibility tree.
 *
 * Both components make explicit accessibility claims in their own docstrings —
 * that errors are linked with `aria-describedby`, that the field is marked
 * `aria-invalid`, that a tone is never carried by colour alone. **Nothing has
 * ever checked any of them.** They were written at M2 with no runner.
 *
 * Queried by role and label rather than by class name or test id, deliberately:
 * a test that finds an input by `.border-danger` passes while the label is
 * detached and a screen reader announces nothing. Querying the way assistive
 * technology does is what makes these tests about the claim rather than about
 * the markup.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

describe("Field", () => {
  it("associates its label with its input", () => {
    // The whole reason `useId` is here. A label that is not associated is a
    // label a screen reader does not read when the input is focused, and it
    // also breaks clicking the label to focus the field.
    render(<Field label="Email" name="email" value="" onChange={vi.fn()} required />);

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("reports the user's typing back to the caller", async () => {
    const onChange = vi.fn();
    render(<Field label="Email" name="email" value="" onChange={onChange} required />);

    await userEvent.type(screen.getByLabelText("Email"), "a");

    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("marks an errored field invalid", () => {
    render(
      <Field
        label="Email"
        name="email"
        value="nope"
        onChange={vi.fn()}
        errors={["Enter a valid email address."]}
        required
      />,
    );

    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("is not invalid when there are no errors", () => {
    // The negative. `aria-invalid="true"` on every field is the same as on
    // none of them.
    render(<Field label="Email" name="email" value="" onChange={vi.fn()} required />);

    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "false");
  });

  it("links the error message to the input", () => {
    // "A visible red border tells a sighted user something is wrong and tells
    // a screen-reader user nothing." This is the claim, and it was unverified.
    render(
      <Field
        label="Email"
        name="email"
        value="nope"
        onChange={vi.fn()}
        errors={["Enter a valid email address."]}
        required
      />,
    );

    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription(
      /Enter a valid email address/,
    );
  });

  it("announces errors, because they appear after focus has moved on", () => {
    render(
      <Field
        label="Email"
        name="email"
        value="nope"
        onChange={vi.fn()}
        errors={["Enter a valid email address."]}
        required
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
  });

  it("links a hint too, and both at once", () => {
    // `aria-describedby` takes a space-separated list. Getting this wrong
    // silently drops one of the two, and which one it drops is not obvious.
    render(
      <Field
        label="Password"
        name="password"
        type="password"
        value="x"
        onChange={vi.fn()}
        hint="At least 12 characters."
        errors={["Too short."]}
        required
      />,
    );

    const description = screen.getByLabelText("Password").getAttribute("aria-describedby");

    expect(description?.split(" ")).toHaveLength(2);
  });

  it("has no description when it has neither", () => {
    // An empty `aria-describedby=""` is not the same as no attribute: it makes
    // some screen readers announce an empty description.
    render(<Field label="Email" name="email" value="" onChange={vi.fn()} required />);

    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-describedby");
  });

  it("marks an optional field optional in its label, not only visually", () => {
    render(<Field label="Display name" name="name" value="" onChange={vi.fn()} />);

    expect(screen.getByLabelText(/optional/i)).toBeInTheDocument();
  });
});

describe("Notice", () => {
  it("announces an error assertively", () => {
    // "An error usually means the thing the user just tried failed, and they
    // should not discover that only when they next tab somewhere."
    render(<Notice tone="error">That did not work.</Notice>);

    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
  });

  it("announces a success politely", () => {
    // The twin. Assertive on a success interrupts whatever the user is doing
    // to tell them something went right, which is how live regions get
    // switched off.
    render(<Notice tone="success">Saved.</Notice>);

    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("hides its decorative symbol from assistive technology", () => {
    // The symbol carries the same meaning as the role and the colour. Read
    // aloud, "exclamation mark" before every error message is noise.
    const { container } = render(<Notice tone="error">That did not work.</Notice>);

    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("!");
  });

  it("distinguishes its tones by more than colour", () => {
    // "Colour alone is not an indicator anyone with a colour-vision deficiency
    // can rely on." Error and success must differ in the accessibility tree,
    // not only in a Tailwind class.
    const { unmount } = render(<Notice tone="error">Bad.</Notice>);
    expect(screen.queryByRole("alert")).toBeInTheDocument();
    unmount();

    render(<Notice tone="success">Good.</Notice>);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
