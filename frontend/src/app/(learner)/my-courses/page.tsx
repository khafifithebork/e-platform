import type { Metadata } from "next";

import { MyCourses } from "@/components/learn/MyCourses";
import { PageTitle } from "@/components/ui/PageTitle";

/**
 * The page the header has linked to since T2 and which did not exist until now.
 *
 * In `(learner)`, not `(marketing)`: it is per-user and can never be
 * prerendered, and M15's structural tests would fail if it sat in the static
 * group. Nothing is fetched here — `MyCourses` is a client component, so no
 * Server Component reaches Django and §11 #5 stays moot under B-lite.
 *
 * No `<main>` of its own: `SiteShell` owns that landmark as of T9, and two on
 * one page is what the document-structure check caught the moment the learner
 * layout was added.
 */
export const metadata: Metadata = {
  title: "My courses",
};

export default function MyCoursesPage() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-10 px-6 py-10 sm:py-16">
      <div className="flex items-start justify-between gap-6">
        <div className="flex min-w-0 flex-col gap-3">
          <PageTitle>My courses</PageTitle>
          <p className="max-w-lg leading-relaxed text-ink-muted">Pick up where you left off, one lesson at a time.</p>
        </div>
        <span aria-hidden="true" className="ink-spots w-16 shrink-0 sm:w-24" />
      </div>
      <MyCourses />
    </div>
  );
}
