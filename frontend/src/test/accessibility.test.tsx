/**
 * axe over the components, one layer of a three-layer check.
 *
 * `src/test/axe.ts` explains which rules are switched off here and why —
 * `contrast.test.ts` owns the palette and `verify:a11y` owns page structure, so
 * this file is for what is wrong in the markup itself: ARIA validity, a widget's
 * name and role, label association, duplicate ids, nesting.
 *
 * **Every state, not just the resting one.** A component's accessible markup
 * usually breaks in the state nobody renders in a screenshot — pending, error,
 * empty, refused — which is also where this project has found most of its faults.
 */

import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageTitle } from "@/components/ui/PageTitle";
import { axeViolations } from "@/test/axe";

afterEach(() => {
  vi.restoreAllMocks();
});

/** Render, run axe, and report the rule and markup rather than a bare boolean. */
async function expectNoViolations(ui: React.ReactElement) {
  const { container } = render(ui);
  expect(await axeViolations(container)).toEqual([]);
}

describe("the primitives", () => {
  it("Button, in every state it has", async () => {
    await expectNoViolations(
      <>
        <Button>Rest</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button size="sm">Small</Button>
        <Button disabled>Disabled</Button>
        <Button pending pendingLabel="Working…">
          Pending
        </Button>
      </>,
    );
  });

  it("Field, including the states that carry the ARIA", async () => {
    // The error state is the one worth checking: `aria-describedby` pointing at an
    // id that does not exist is a broken reference axe catches and a human reading
    // the JSX usually does not.
    await expectNoViolations(
      <>
        <Field label="Email" name="email" value="" onChange={() => {}} required />
        <Field
          label="Password"
          name="password"
          type="password"
          value=""
          onChange={() => {}}
          hint="At least 8 characters."
          errors={["That password is too common."]}
          required
        />
        <Field label="Optional note" name="note" value="" onChange={() => {}} />
        <Field label="Locked" name="locked" value="" onChange={() => {}} disabled required />
      </>,
    );
  });

  it("Notice, both tones, with and without a title", async () => {
    await expectNoViolations(
      <>
        <Notice tone="error">Something went wrong.</Notice>
        <Notice tone="success" title="Almost there">
          Check your inbox.
        </Notice>
      </>,
    );
  });

  it("Card, Badge and PageTitle", async () => {
    await expectNoViolations(
      <>
        <PageTitle>A destination</PageTitle>
        <Card as="article" aria-labelledby="t" hoverable>
          <h2 id="t">A card</h2>
          <Badge>A2</Badge>
        </Card>
      </>,
    );
  });
});

describe("two fields with the same label", () => {
  it("do not collide on id, because ids come from useId", async () => {
    /**
     * `Field` builds its ids with `useId`, and this is what that buys: two fields
     * with identical labels on one page produce distinct `for`/`id` pairs. Written
     * the obvious way — an id derived from `name`, or a module-level counter — this
     * is where it breaks, and the symptom is a label that focuses the wrong input.
     * `duplicate-id` catches it.
     */
    await expectNoViolations(
      <>
        <Field label="Email" name="email" value="" onChange={() => {}} required />
        <Field label="Email" name="email_confirm" value="" onChange={() => {}} required />
      </>,
    );
  });
});

describe("the helper itself", () => {
  it("reports a violation when there is one", async () => {
    /**
     * The twin, and this file needs it more than most. Everything above asserts an
     * empty array — which is exactly what a misconfigured axe, a wrong container or
     * a helper that swallowed its results would also produce. So: markup that is
     * definitely wrong, and it must be caught.
     */
    const { container } = render(
      <button aria-labelledby="nothing-points-here">
        {/* Deliberately broken: no `alt`, and an `aria-labelledby` pointing at an
            id that does not exist. ESLint's own accessibility rules object to this
            markup, which is the point of it — they are disabled for this one
            element rather than the file, so the rest still benefits from them. */}
        {/* eslint-disable-next-line jsx-a11y/alt-text, @next/next/no-img-element */}
        <img src="/x.png" />
      </button>,
    );

    const violations = await axeViolations(container);

    expect(violations.length).toBeGreaterThan(0);
    expect(violations.map((v) => v.id)).toContain("image-alt");
  });

  it("does not report the rules it deliberately switched off", async () => {
    /**
     * A fragment with no `<main>`, no `<h1>` and no `lang` is correct for a
     * component, and the page-level rules would fail on it. If a future axe version
     * renames one of those rules, this test goes red rather than the whole suite
     * quietly failing on correct components — which is the failure mode worth
     * catching, because the response would otherwise be to weaken the check.
     */
    const { container } = render(
      <div>
        <p>A fragment, quite legitimately lacking a page around it.</p>
      </div>,
    );

    const ids = (await axeViolations(container)).map((v) => v.id);

    expect(ids).not.toContain("region");
    expect(ids).not.toContain("landmark-one-main");
    expect(ids).not.toContain("page-has-heading-one");
    expect(ids).not.toContain("color-contrast");
  });
});

/**
 * The domain components whose markup carries real ARIA.
 *
 * Fixtures only — no network. The interesting ones are the accordion and the
 * cards: an accordion is where `aria-expanded`, `aria-controls` and the
 * button-versus-heading question all meet, and a card is where a heading level
 * and an `aria-labelledby` have to agree.
 */
describe("the domain components", () => {
  const COURSE = {
    id: "id-spanish",
    slug: "spanish",
    title: "Spanish for beginners",
    description: "Reviewed before publication.",
    language: "es",
    level: "A1",
    skill_areas: ["speaking"],
    instructor_name: "A. Teacher",
    published_at: "2026-08-01T00:00:00Z",
  } as never;

  const SECTIONS = [
    {
      id: "s1",
      title: "Getting started",
      position: 1,
      lessons: [
        { id: "l1", title: "The alphabet", position: 1, slug: "alphabet", is_preview: true },
        { id: "l2", title: "Saying hello", position: 2, slug: "hello", is_preview: false },
      ],
    },
    { id: "s2", title: "Greetings", position: 2, lessons: [] },
  ] as never;

  it("CourseCard, at both heading levels it is used at", async () => {
    const { CourseCard } = await import("@/components/catalogue/CourseCard");
    await expectNoViolations(
      <>
        <h1>Courses</h1>
        <CourseCard course={COURSE} headingLevel={2} />
        <h2>Related</h2>
        <CourseCard course={COURSE} headingLevel={3} />
      </>,
    );
  });

  it("Curriculum, expanded and collapsed", async () => {
    // The accordion's resting state is expanded, so a plain render covers that;
    // clicking a section header covers the other. Both matter, because
    // `aria-expanded` is the attribute most likely to be right in one state only.
    const { Curriculum } = await import("@/components/catalogue/Curriculum");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { container, getByRole } = render(
      <Curriculum sections={SECTIONS} courseSlug="spanish" />,
    );

    expect(await axeViolations(container)).toEqual([]);

    await userEvent.setup().click(getByRole("button", { name: /getting started/i }));
    expect(await axeViolations(container)).toEqual([]);
  });

  it("NotFoundContent", async () => {
    const { NotFoundContent } = await import("@/components/NotFoundContent");
    await expectNoViolations(<NotFoundContent />);
  });

  it("PricingPlans, both the unannounced state and a priced one", async () => {
    /**
     * `prices={null}` is what the page renders today — `PRICE_BOOK` stays null
     * until the payment-provider question is answered (§11 #1) — so it is the state
     * that actually ships. The priced branch is checked too, because it is the one
     * nobody has ever seen and the one M8 will turn on.
     */
    const { PricingPlans } = await import("@/components/pricing/PricingPlans");

    await expectNoViolations(<PricingPlans prices={null} />);
    await expectNoViolations(
      <PricingPlans
        prices={{
          monthly: { amount: 990, currency: "EUR" },
          yearly: { amount: 9900, currency: "EUR" },
          trialDays: 7,
        }}
      />,
    );
  });
});
