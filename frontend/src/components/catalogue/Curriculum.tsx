"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import type { PublicSection } from "@/lib/catalogue/courses";

/**
 * The course outline, as an anonymous visitor sees it — collapsible per
 * section, everything expanded on load.
 *
 * **Structure only — there is no lesson body here to leak.** `PublicLesson`
 * has no `body` field at all; the serializer's own docstring says it is
 * "absent from `fields`, not hidden by a condition", because "a field that is
 * usually hidden is one wrong branch from being visible". So abuse case 3 is
 * satisfied upstream, and this component could not render paid content if it
 * tried. The test for it asserts that rather than trusting it.
 *
 * **Every section starts open, not closed.** The obvious accordion default —
 * collapsed, click to reveal — would hide the whole curriculum behind an
 * interaction on the one page whose entire job is telling an undecided
 * visitor what is in the course. Collapsing is something to *do*, offered for
 * a long course where scanning chapter titles alone is useful; it is not the
 * resting state of a page abuse case 3 depends on being fully readable.
 *
 * The WAI-ARIA disclosure pattern — a `<button>` inside the `<h3>`, wired
 * with `aria-expanded` and `aria-controls` — rather than a click handler on
 * the heading itself, which is not a focusable, announced control on its own.
 *
 * Ordered by `position`, which is the field the backend maintains for
 * exactly this — relying on array order would mean the outline silently
 * reshuffles the day the API changes its default ordering.
 */
export function Curriculum({
  sections,
  courseSlug,
}: {
  sections: PublicSection[];
  /** Needed to build lesson links — a lesson URL is course-scoped. */
  courseSlug: string;
}) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());

  function toggle(sectionId: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(sectionId)) next.delete(sectionId);
      else next.add(sectionId);
      return next;
    });
  }

  if (sections.length === 0) {
    // An approved course with no sections is possible and looks like a bug to
    // a visitor. Saying so is better than an empty heading with nothing
    // underneath it.
    return <p className="text-ink-muted">The outline for this course is not published yet.</p>;
  }

  const ordered = [...sections].sort((a, b) => a.position - b.position);

  return (
    <ol className="divide-y divide-line border-y border-line">
      {ordered.map((section, index) => {
        const open = !collapsed.has(section.id);
        const panelId = `curriculum-section-${section.id}`;

        return (
          <li
            key={section.id}
            className="min-w-0 py-2 [overflow-wrap:anywhere]"
          >
            <h3>
              <button
                type="button"
                onClick={() => toggle(section.id)}
                aria-expanded={open}
                aria-controls={panelId}
                className="flex min-h-12 w-full items-center gap-3 rounded-(--radius-sm) py-3
                  text-start font-display text-lg text-ink transition-colors
                  hover:text-accent"
              >
                {/*
                 * The number is decorative — an ordered list already conveys
                 * position to assistive technology, so reading "1. Section
                 * one. List item one of four" is the same fact twice.
                 */}
                <span aria-hidden="true" className="text-ink-subtle">
                  {index + 1}.
                </span>
                <span className="flex-1">{section.title}</span>
                <ChevronDown
                  aria-hidden="true"
                  size={18}
                  className={`shrink-0 text-ink-subtle ${open ? "" : "-rotate-90"}`}
                />
              </button>
            </h3>

            <div
              id={panelId}
              hidden={!open}
            >
              <ul className="mb-3 flex flex-col border-s border-line ps-4 sm:ms-6">
                {[...section.lessons]
                  .sort((a, b) => a.position - b.position)
                  .map((lesson) => (
                    <li key={lesson.id} className="flex flex-wrap items-center gap-x-3 text-sm">
                      {/*
                       * Lessons are links as of M16 T3, and they were
                       * deliberately not links before.
                       *
                       * The original reasoning was that "a link here would
                       * invite a signed-out visitor into an entitlement
                       * refusal". That held while a refusal was a bare 403
                       * with nowhere to go. It no longer does: a preview
                       * lesson plays for somebody with no account at all, and
                       * every refusal now lands on a page that says what
                       * happened and offers a way forward.
                       *
                       * A curriculum whose lessons cannot be opened is a
                       * table of contents for a book nobody can reach.
                       */}
                      <Link
                        href={`/courses/${courseSlug}/lessons/${lesson.slug}`}
                        className="flex min-h-11 min-w-0 items-center py-2 text-ink-muted underline-offset-4 hover:text-accent hover:underline"
                      >
                        {lesson.title}
                      </Link>

                      {lesson.is_preview && <Badge tone="accent">Free preview</Badge>}
                    </li>
                  ))}
              </ul>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
