import { SiteShell } from "@/components/site/SiteShell";

/**
 * The public shell.
 *
 * architecture.md:937 put "landing, pricing, public course pages" in a
 * `(marketing)` route group at M0 and nothing was built in it until M15.
 * CLAUDE.md invariant 15 is what shapes it: **nothing under here may fetch at
 * request time**, which is why every page in this group is statically
 * generated and this layout holds navigation and no data.
 *
 * That is not a performance preference. A request-time fetch here would cross
 * the public internet under B-lite (ADR-025) — Next on Cloudflare Workers,
 * Django on Hetzner, no private network between them — and would need its own
 * authentication. Keeping this layout data-free is what keeps §11 #5 moot.
 *
 * **The markup moved to `SiteShell` at M16 T9.** It lived here until the
 * learner pages turned out to have no chrome at all, and two layouts that look
 * alike drift — the half that drifts being the one nobody has open when they
 * change the other.
 */
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <SiteShell>{children}</SiteShell>;
}
