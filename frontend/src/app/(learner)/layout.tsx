import { SiteShell } from "@/components/site/SiteShell";

/**
 * The same chrome the public pages wear.
 *
 * **These pages had none until M16 T9.** `(learner)` was created at T3 for the
 * lesson route and gained "my courses" at T5, and neither task noticed the
 * group had no layout — so a learner who followed "My courses" out of the
 * header arrived at a page with no header, no footer, no navigation and no
 * skip link. Browser-back was the only way out.
 *
 * Found by reading the built HTML rather than the source. The whole document
 * was: *"My courses · Lingua / My courses / Loading your courses…"*.
 *
 * Unlike `(marketing)`, nothing here is statically generated and nothing here
 * needs to be — every page is per-user. The shell is identical anyway, because
 * a learner crossing between the catalogue and their own courses should not
 * feel they have left the site.
 */
export default function LearnerLayout({ children }: { children: React.ReactNode }) {
  return <SiteShell>{children}</SiteShell>;
}
