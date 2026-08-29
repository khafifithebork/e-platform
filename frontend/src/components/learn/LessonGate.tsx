"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { LessonPlayer } from "@/components/learn/LessonPlayer";
import { ApiError, api, type GatedLesson } from "@/lib/api/client";
import { refusalFor } from "@/lib/entitlements/denial";

/**
 * Resolves two slugs to a lesson, then hands over to the player.
 *
 * **Why this exists rather than the player taking slugs directly.** Everything
 * the player does after loading — progress, completion, the playback token,
 * the transcript — is addressed by lesson *id*, in eleven places. Teaching a
 * 367-line component with no tests to carry a resolved id was not the right
 * change to make inside a routing task. T6 owns the player, will have tests
 * around it, and is where that belongs.
 *
 * **The lesson is passed down, not refetched.** T3 shipped this resolving the
 * lesson and then letting the player fetch the same one again — two gated GETs
 * where one would do — and wrote that down as a temporary cost. T6 removed it:
 * the player takes the resolved lesson as a prop.
 *
 * **Each of the six refusals has its own wording**, from `lib/entitlements/denial`.
 * `resolve_access` returns a reason and never a bare boolean (invariant 3), and
 * six reasons exist precisely so an interface can say six different things.
 */
type GateState =
  | { status: "loading" }
  | { status: "ready"; lesson: GatedLesson }
  | { status: "missing" }
  | { status: "refused"; reason: string; cta: string | null }
  | { status: "failed" };

export function LessonGate({
  courseSlug,
  lessonSlug,
}: {
  courseSlug: string;
  lessonSlug: string;
}) {
  const [state, setState] = useState<GateState>({ status: "loading" });

  useEffect(() => {
    let current = true;

    api
      .lessonBySlug(courseSlug, lessonSlug)
      .then((lesson) => {
        if (current) setState({ status: "ready", lesson });
      })
      .catch((error: unknown) => {
        if (!current) return;

        if (error instanceof ApiError) {
          // 404 covers both "no such lesson" and "the course is not
          // published", and the API conflates them on purpose — §6.3, because
          // a 403 would confirm that an unreleased course exists.
          if (error.problem.status === 404) {
            setState({ status: "missing" });
            return;
          }

          const reason = error.entitlementReason;
          if (reason) {
            const cta = (error.problem as { cta?: unknown }).cta;
            setState({
              status: "refused",
              reason,
              cta: typeof cta === "string" ? cta : null,
            });
            return;
          }
        }

        setState({ status: "failed" });
      });

    return () => {
      current = false;
    };
  }, [courseSlug, lessonSlug]);

  if (state.status === "loading") {
    // A live region, because the rest of the page is empty while this
    // resolves: a screen-reader user gets no signal at all that anything is
    // happening otherwise.
    return (
      <main className="mx-auto w-full max-w-6xl px-6 py-10">
        <p aria-live="polite" className="text-ink-muted">
          Loading the lesson…
        </p>
      </main>
    );
  }

  if (state.status === "ready") {
    return (
      <main className="mx-auto w-full max-w-6xl px-6 py-10">
        <nav aria-label="Breadcrumb" className="mb-6 text-sm">
          {/*
           * Back to the course, not back to the catalogue. Somebody who
           * reached a lesson and wants out almost always wants the thing it
           * belongs to — and `course_slug` on the lesson makes it one hop
           * rather than a guess from the URL.
           */}
          <Link
            href={`/courses/${state.lesson.course_slug}`}
            className="text-ink-muted hover:text-ink"
          >
            ← Back to the course
          </Link>
        </nav>

        <LessonPlayer lesson={state.lesson} />
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-6 py-16">
      {state.status === "missing" && (
        <>
          <h1 className="font-display text-3xl tracking-tight text-ink">
            That lesson is not here
          </h1>
          <p className="text-ink-muted">
            The link may be old, or the course may have been taken down.
          </p>
        </>
      )}

      {state.status === "refused" && <Refused reason={state.reason} />}

      {state.status === "failed" && (
        <>
          <h1 className="font-display text-3xl tracking-tight text-ink">
            This lesson could not be loaded
          </h1>
          <p className="text-ink-muted">Something went wrong. Try again in a moment.</p>
        </>
      )}

      <Link href={`/courses/${courseSlug}`} className="text-ink-muted hover:text-ink">
        ← Back to the course
      </Link>
    </main>
  );
}

/**
 * One refusal, said in its own words.
 *
 * `GRACE_PERIOD_ENDED` deliberately has no action link. The person is a paying
 * customer whose payment failed, and the only useful destination is a page for
 * updating payment details — which does not exist, because there is no billing
 * surface until M8. A link to `/pricing` would tell somebody to buy what they
 * have already bought.
 */
function Refused({ reason }: { reason: string }) {
  const refusal = refusalFor(reason);

  return (
    <>
      <h1 className="font-display text-3xl tracking-tight text-ink">{refusal.title}</h1>
      <p className="text-ink-muted">{refusal.detail}</p>

      {refusal.action && (
        <Link href={refusal.action.href} className="text-accent hover:text-accent-hover">
          {refusal.action.label}
        </Link>
      )}
    </>
  );
}
