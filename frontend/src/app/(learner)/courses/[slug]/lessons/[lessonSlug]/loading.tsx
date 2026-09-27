/**
 * The lesson route's loading state.
 *
 * ADR-031 §2: this is the **only** place in the product where a `loading.tsx`
 * earns its place, because it is the only dynamic route (ADR-026). Everything
 * else is prerendered, so a boundary there would flash for a frame or never
 * appear at all.
 *
 * **An `aria-live` region with text, not a bare spinner.** The convention every
 * loading state in this app follows, and ADR-026 has the reason: the rest of the
 * page is empty while this resolves, so a screen-reader user otherwise gets no
 * signal that anything is happening. `LessonGate` says the same words for the
 * same reason once it is mounted; this covers the gap before it is.
 *
 * **The empty box below the message is deliberate.** It reserves roughly the
 * player's height so the page does not jump when content arrives — the layout
 * stability concern ADR-031 names. `aria-hidden`, because it stands for
 * something that has not loaded and announcing it would be describing furniture.
 *
 * A Server Component: no interactivity, so no `"use client"`. That also keeps it
 * out of the client bundle, which matters slightly more here than elsewhere —
 * this is the one route a learner waits on.
 */
export default function LessonLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <p aria-live="polite" className="text-ink-muted">
        Loading the lesson…
      </p>

      <div
        aria-hidden="true"
        className="mt-6 aspect-video w-full rounded-(--radius-lg) border border-line
          bg-surface-sunken"
      />
    </div>
  );
}
