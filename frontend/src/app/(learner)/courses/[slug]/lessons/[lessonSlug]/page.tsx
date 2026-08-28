import type { Metadata } from "next";

import { LessonGate } from "@/components/learn/LessonGate";

/**
 * A lesson, at the URL architecture.md §6.2 always meant it to have.
 *
 * `/courses/{slug}/lessons/{lessonSlug}` — shareable, readable, and stable
 * across a lesson being re-created. It replaces `/learn/{uuid}`, which the old
 * page's own docstring described as provisional: *"there is no course page yet
 * to link from. The nicer URL belongs with the catalogue pages."* M15 built
 * those pages.
 *
 * **In a `(learner)` route group, not `(marketing)`.** The URL sits inside
 * `/courses/`, which is otherwise statically generated, and a gated page cannot
 * be. Route groups do not appear in the URL, so this shares the path space
 * without sharing the constraint — and M15's structural tests, which forbid a
 * `fetch` or a `"use client"` anywhere under `(marketing)`, keep applying to
 * the static pages beside it.
 *
 * Nothing is fetched here. `LessonGate` is a client component: the page is
 * authenticated and personal, so it can never be prerendered, and CLAUDE.md
 * §11 #5 stays moot because no Server Component reaches Django.
 */
export const metadata: Metadata = {
  // No lesson title. Naming the tab would mean fetching the lesson on the
  // server for every visitor including ones with no right to it — an
  // authenticated fetch from the server tier, which under B-lite (ADR-025)
  // crosses the public internet. The client fetches it a moment later anyway.
  title: "Lesson",
};

export default async function LessonPage({
  params,
}: {
  params: Promise<{ slug: string; lessonSlug: string }>;
}) {
  const { slug, lessonSlug } = await params;

  return <LessonGate courseSlug={slug} lessonSlug={lessonSlug} />;
}
