import type { Metadata } from "next";

import { LessonPlayer } from "@/components/learn/LessonPlayer";

/**
 * The lesson page.
 *
 * Addressed by lesson id rather than `/courses/{slug}/lessons/{slug}`, because
 * that is how the API addresses a lesson and there is no course page yet to
 * link from. The nicer URL belongs with the catalogue pages.
 *
 * Outside the `(marketing)` group on purpose: invariant 15 requires that group
 * to be statically generated with no request-time API call, and this page is
 * authenticated, personal and cannot be either.
 */
export const metadata: Metadata = {
  // No lesson title: fetching it here to name the tab would call the API at
  // request time for every visitor, including ones with no right to the
  // lesson, and the player already fetches it.
  title: "Lesson",
};

export default async function LessonPage({
  params,
}: {
  params: Promise<{ lessonId: string }>;
}) {
  const { lessonId } = await params;

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <LessonPlayer lessonId={lessonId} />
    </main>
  );
}
