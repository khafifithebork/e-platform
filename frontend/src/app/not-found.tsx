import { NotFoundContent } from "@/components/NotFoundContent";

/**
 * The site-wide 404, and the one that does most of the work.
 *
 * Without this file, Next serves its own: an unstyled white page reading "404
 * — This page could not be found", with no navigation off it. That is what
 * this site served for every unknown URL until M15 T9, and — the part that was
 * not obvious — for every **refused course slug** too, because
 * `dynamicParams = false` rejects those in the router before any route group's
 * `not-found.tsx` can run.
 *
 * Rendered in the root layout, so it has no site header. That is a real
 * limitation and not worth fixing by moving the header up: the header belongs
 * to the marketing group, and hoisting it into the root layout would put it on
 * the auth pages and the lesson player too.
 */
export default function NotFound() {
  return <NotFoundContent />;
}
