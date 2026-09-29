/**
 * The data-export control, and the two claims it must not make.
 *
 * It is a plain link rather than a fetch — `src/components/account/DataExport.tsx`
 * explains why — so there is little behaviour to test and two properties that matter
 * a great deal:
 *
 * 1. It points at the real endpoint, same-origin, so the session cookie rides along.
 * 2. **It does not invent a support channel.** The first draft said "email support",
 *    and there is no support address anywhere in this repository. Publishing one
 *    would be a support commitment nobody has made, and CLAUDE.md §6 forbids
 *    inventing facts about the product.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataExport } from "@/components/account/DataExport";
import { axeViolations } from "@/test/axe";

describe("the download", () => {
  it("links to the export endpoint on this origin", () => {
    /**
     * Relative, so it goes through the Next rewrite to Django and the session cookie
     * is sent. An absolute URL to another origin would be a cross-origin request
     * without credentials, which answers 403 — and the symptom is a downloaded file
     * containing a refusal.
     */
    render(<DataExport />);

    const link = screen.getByRole("link", { name: /download my data/i });

    expect(link).toHaveAttribute("href", "/api/v1/auth/me/export/");
    expect(link).toHaveAttribute("download");
  });

  it("says what the file contains and what it leaves out", () => {
    // Somebody exercising a data-access right needs to know the scope of what they
    // are getting. "Course content is not included" is the one exclusion they would
    // otherwise expect to find.
    render(<DataExport />);

    expect(screen.getByText(/course content is not included/i)).toBeVisible();
  });
});

describe("what it does not claim", () => {
  it("names no support address, because there is not one", () => {
    /**
     * **The property this file exists for.** A published address nobody reads is
     * worse than an admitted gap: it invites people to write about their data rights
     * into a void. Asserted as the absence of any address at all, so a later draft
     * cannot reintroduce one without this failing.
     */
    const { container } = render(<DataExport />);
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/@/);
    expect(text).not.toMatch(/email (us|support)/i);
    expect(text).not.toMatch(/contact (us|support) at/i);
  });

  it("does not offer or promise account deletion", () => {
    /**
     * `docs/specs/m10-admin.md` §6 deferred erasure, and what survives one —
     * invoices, the audit trail, instructor-authored content — is a retention
     * question with legal weight. A button in front of an unanswered question is
     * worse than no button, and so is a promised date.
     */
    render(<DataExport />);

    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /delete/i })).toBeNull();
    // States the absence without claiming when it will change.
    expect(screen.getByText(/not yet something this site can do/i)).toBeVisible();
  });

  it("says the gap out loud rather than staying silent about it", () => {
    // The twin for the two negatives above: a component that simply omitted any
    // mention of deletion would satisfy both, and leave somebody looking for a
    // control that is not there.
    const { container } = render(<DataExport />);

    expect(container.textContent ?? "").toMatch(/deleting an account/i);
  });
});

describe("the markup", () => {
  it("has no axe violations", async () => {
    const { container } = render(<DataExport />);

    expect(await axeViolations(container)).toEqual([]);
  });
});
