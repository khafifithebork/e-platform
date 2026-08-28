import type { PublicSection } from "@/lib/catalogue/courses";

/**
 * The course outline, as an anonymous visitor sees it.
 *
 * **Structure only — there is no lesson body here to leak.** `PublicLesson`
 * has no `body` field at all; the serializer's own docstring says it is
 * "absent from `fields`, not hidden by a condition", because "a field that is
 * usually hidden is one wrong branch from being visible". So abuse case 3 is
 * satisfied upstream, and this component could not render paid content if it
 * tried. The test for it asserts that rather than trusting it.
 *
 * Server-rendered, no state. Ordered by `position`, which is the field the
 * backend maintains for exactly this — relying on array order would mean the
 * outline silently reshuffles the day the API changes its default ordering.
 */
export function Curriculum({ sections }: { sections: PublicSection[] }) {
  if (sections.length === 0) {
    // An approved course with no sections is possible and looks like a bug to
    // a visitor. Saying so is better than an empty heading with nothing
    // underneath it.
    return <p className="text-ink-muted">The outline for this course is not published yet.</p>;
  }

  const ordered = [...sections].sort((a, b) => a.position - b.position);

  return (
    <ol className="flex flex-col gap-6">
      {ordered.map((section, index) => (
        <li key={section.id} className="flex flex-col gap-3">
          <h3 className="font-display text-lg text-ink">
            {/*
             * The number is decorative — an ordered list already conveys
             * position to assistive technology, so reading "1. Section one.
             * List item one of four" is the same fact twice.
             */}
            <span aria-hidden="true" className="mr-2 text-ink-subtle">
              {index + 1}.
            </span>
            {section.title}
          </h3>

          <ul className="flex flex-col gap-1.5 border-l border-line pl-4">
            {[...section.lessons]
              .sort((a, b) => a.position - b.position)
              .map((lesson) => (
                <li key={lesson.id} className="flex items-baseline gap-2 text-sm">
                  <span className="text-ink-muted">{lesson.title}</span>

                  {/*
                   * A preview lesson is watchable without a subscription, and
                   * that is the single most useful thing this page can tell
                   * somebody deciding whether to pay. It is a badge rather than
                   * a link: the lesson route is entitlement-gated and lives
                   * outside this route group.
                   */}
                  {lesson.is_preview && (
                    <span
                      className="rounded-[--radius-sm] bg-accent-subtle px-1.5 py-0.5
                        text-xs font-medium text-accent"
                    >
                      Free preview
                    </span>
                  )}
                </li>
              ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}
