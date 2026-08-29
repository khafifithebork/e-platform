import type { Metadata } from "next";

import { MyCourses } from "@/components/learn/MyCourses";

/**
 * The page the header has linked to since T2 and which did not exist until now.
 *
 * In `(learner)`, not `(marketing)`: it is per-user and can never be
 * prerendered, and M15's structural tests would fail if it sat in the static
 * group. Nothing is fetched here — `MyCourses` is a client component, so no
 * Server Component reaches Django and §11 #5 stays moot under B-lite.
 */
export const metadata: Metadata = {
  title: "My courses",
};

export default function MyCoursesPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-16">
      <h1 className="font-display text-4xl tracking-tight text-ink">My courses</h1>
      <MyCourses />
    </main>
  );
}
