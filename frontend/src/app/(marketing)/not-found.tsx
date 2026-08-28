import { NotFoundContent } from "@/components/NotFoundContent";

/**
 * A 404 raised while rendering a page in this group.
 *
 * In practice that means `courses/[slug]` calling `notFound()` because the API
 * answered 404 for a course during the build — a course unpublished between
 * the listing read and the detail read.
 *
 * **It does not serve refused slugs.** `dynamicParams = false` refuses those in
 * the router, before this segment renders; `app/not-found.tsx` handles them.
 * Verified against a running build rather than assumed — see
 * `components/NotFoundContent.tsx`.
 *
 * Kept anyway, because it renders inside the marketing shell: an in-segment
 * 404 keeps the header and footer, which the site-wide one cannot.
 */
export default function MarketingNotFound() {
  return <NotFoundContent />;
}
