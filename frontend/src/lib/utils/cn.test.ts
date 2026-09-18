/**
 * Class merging, and the one behaviour it exists for.
 *
 * `clsx` alone would return both of two conflicting Tailwind utilities and
 * leave the outcome to stylesheet order — which is how a `className` override
 * passed by a caller silently loses to the component's own base class. The
 * `twMerge` half is what makes `cn(base, className)` mean what it looks like
 * it means, and it is the part a future "this dependency seems unnecessary"
 * would remove.
 */

import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils/cn";

describe("cn", () => {
  it("lets a later utility win over an earlier conflicting one", () => {
    // The whole reason twMerge is here. Without it this returns both.
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("keeps utilities that do not conflict", () => {
    // The twin: a function that simply returned its last argument would pass
    // the test above and throw away every base class a component sets.
    expect(cn("rounded-md", "px-4")).toBe("rounded-md px-4");
  });

  it("drops falsy conditionals rather than rendering them", () => {
    expect(cn("base", false && "hidden", undefined, null)).toBe("base");
  });

  it("accepts the conditional-object form", () => {
    expect(cn("base", { active: true, disabled: false })).toBe("base active");
  });
});
