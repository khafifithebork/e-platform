"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { LoadFailure } from "@/components/ui/LoadFailure";
import { Notice } from "@/components/ui/Notice";
import { PageTitle } from "@/components/ui/PageTitle";
import { refusalFor } from "@/lib/entitlements/denial";
import { TranscriptPanel } from "@/components/learn/TranscriptPanel";
import {
  ApiError,
  api,
  beaconProgress,
  type GatedLesson,
  type LessonProgress,
  type PlaybackToken,
  type TranscriptSegment,
} from "@/lib/api/client";
import { BEAT_SECONDS, watchedSince, worthSending } from "@/lib/learn/heartbeat";
import {
  DEFAULT_PLAYBACK_RATE,
  PLAYBACK_RATES,
  REPLAY_SECONDS,
  type PlaybackRate,
  readPlaybackRate,
  replayFrom,
  writePlaybackRate,
} from "@/lib/learn/preferences";

/**
 * How a playback id becomes a URL, if a provider is configured.
 *
 * Read from the environment rather than written here, because **we do not
 * know it**: M5 shipped a fake video provider deliberately (zero spend), and
 * the real provider has not been chosen. Guessing a URL shape from memory is
 * exactly the fabricated provider capability CLAUDE.md §6 forbids.
 *
 * With no template the page falls back to a stand-in clock, so the watch loop
 * is still demonstrable end to end — which is the whole point of this page
 * (ADR-016 §4).
 */
const PLAYBACK_URL_TEMPLATE = process.env.NEXT_PUBLIC_PLAYBACK_URL_TEMPLATE ?? "";

function playbackUrl(playback: PlaybackToken): string | null {
  if (!PLAYBACK_URL_TEMPLATE) return null;
  return PLAYBACK_URL_TEMPLATE.replace("{playback_id}", playback.playback_id).replace(
    "{token}",
    playback.token,
  );
}

/** `137` → `2:17`. */
function timestamp(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/*
 * The denial messages that used to live here are gone.
 *
 * They were keyed on `SUBSCRIPTION_PAST_DUE` and `NOT_AUTHENTICATED`, **and
 * neither has ever been a `Reason`** — so two branches could not fire, and
 * four real refusals had no branch at all, including `LOGIN_REQUIRED`, which
 * is what every signed-out visitor gets. Written at M7, never tested, never
 * reached by a user, and nothing caught it because the codes were plain
 * strings on both sides.
 *
 * `lib/entitlements/denial` is the one table now, keyed by the schema enum, so
 * a reason added in M8 is a compile error rather than a silent fallback.
 */

interface LessonPlayerProps {
  /**
   * The lesson, already resolved.
   *
   * **Passed in rather than fetched, as of M16 T6.** `LessonGate` resolves
   * `/courses/{slug}/lessons/{lessonSlug}` to learn the id this component
   * addresses everything else by — and until now this component then fetched
   * the very same lesson again. Two gated GETs where one would do, on every
   * lesson load. T3 wrote that down as a temporary cost; this is the task that
   * removes it.
   */
  lesson: GatedLesson;
}

/**
 * One lesson: watch it, read along, and have where you got to survive.
 *
 * Deliberately not a designed product surface (ADR-016 §4). It exists so the
 * milestone's claim — *watch → progress persists → resume across devices* —
 * is something somebody has watched work rather than a sentence in a document.
 *
 * A Client Component in full, which is a departure from "Server Components by
 * default" (CLAUDE.md §13) and worth the sentence: every element here is
 * interactive, the page is authenticated so it can never be statically
 * generated, and the API client is browser-side on purpose so the session
 * cookie is never handled by our code (invariant 9). Server-rendering the
 * shell would mean forwarding a session cookie from the browser to the
 * internal origin — a new auth surface, for a title and a heading. The
 * catalogue pages are the ones that want that pattern, and they are M11.
 *
 * **Completion is displayed, never decided.** The server owns the rule
 * (ADR-016 §2) and returns `completed_at` on every beat; this renders what it
 * is told. A client that decided for itself would be the second definition
 * §10 M7 warns about.
 */
export function LessonPlayer({ lesson }: LessonPlayerProps) {
  const lessonId = lesson.id;
  const [progress, setProgress] = useState<LessonProgress | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  /**
   * The captions' language, for the `<track>` below.
   *
   * **Held rather than discarded, as of 2026-09-29.** This component has fetched
   * `/lessons/{id}/transcript/` since M7 and kept only `segments`, throwing away
   * the `language_code` that was sitting in the same payload — which is why the
   * `<track>` had no `srclang` and why ADR-033 §3 recorded that as blocked on the
   * API. It was not: `Transcript.language` has been a foreign key to `Language`
   * since M6, and this endpoint has carried the code since the panel existed.
   * `language_name` was added alongside it for the `label`.
   */
  const [captions, setCaptions] = useState<{ code: string; name: string } | null>(null);
  const [playback, setPlayback] = useState<PlaybackToken | null>(null);
  const [denial, setDenial] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  /** Bumped to retry a failed load. See `LoadFailure`. */
  const [attempt, setAttempt] = useState(0);

  /** Re-run the load that failed. The reset is here, not in the effect. */
  function retry() {
    setLoading(true);
    setFailure(null);
    setAttempt((n) => n + 1);
  }
  const [completing, setCompleting] = useState(false);

  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);

  /**
   * Playback speed, remembered per device.
   *
   * Initialised in an effect rather than from `useState(readPlaybackRate)`, because
   * reading `localStorage` during render makes the first client render disagree with
   * the server's and React treats that as a hydration mismatch. The lesson page is
   * never server-rendered, but the habit is the one that caused the reduced-motion
   * bug at M15, so it is not repeated here.
   */
  const [rate, setRate] = useState<PlaybackRate>(DEFAULT_PLAYBACK_RATE);
  const rateRef = useRef<number>(DEFAULT_PLAYBACK_RATE);

  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Refs, not state, for everything the ticker touches. The interval is
  // installed once; reading state inside it would close over the values as
  // they were on the first render and report the same beat forever.
  const positionRef = useRef(0);
  const playingRef = useRef(false);
  const unreportedRef = useRef(0);
  const lastSentPositionRef = useRef<number | null>(null);

  // **Do not report a position before reading the stored one.** Without this
  // the loop can write a playhead of zero over a real bookmark: the ticker is
  // installed on mount, its cleanup reports a final beat, and in development
  // React Strict Mode runs that cleanup immediately — before the fetch that
  // says where the learner actually was has come back. Watched live: a lesson
  // resumed at 0:00 instead of 0:46, having just destroyed the one thing this
  // page exists to prove.
  const readyRef = useRef(false);

  const url = playback ? playbackUrl(playback) : null;

  const send = useCallback(
    async (final: boolean) => {
      if (!readyRef.current) return;

      /**
       * Whole seconds only, with the fraction carried.
       *
       * The accumulator became fractional when the speed control arrived — fifteen
       * seconds at 1.5× is 22.5 seconds of content — and `watched_delta_seconds` is
       * an `IntegerField` on the server. The client already rounds, so nothing would
       * have been rejected; it would have **over-claimed half a second on every
       * beat**, which is two minutes an hour, all of it in the same direction.
       *
       * Flooring and carrying the remainder means the total claimed over a lesson
       * is the content time actually watched, whatever the speed — asserted over
       * four beats rather than one, because a single beat cannot show drift.
       */
      const claimable = Math.floor(unreportedRef.current);

      const beat = {
        positionSeconds: positionRef.current,
        watchedDeltaSeconds: claimable,
      };
      if (!worthSending(beat, lastSentPositionRef.current)) return;

      // Deducted before the request, not after. A beat that fails has still
      // consumed that stretch of watching; carrying it forward would let a
      // flaky connection accumulate an hour and then claim it all at once. The
      // sub-second remainder does carry, because it has not been claimed.
      unreportedRef.current -= claimable;
      lastSentPositionRef.current = Math.round(beat.positionSeconds);

      if (final) {
        beaconProgress(lessonId, beat.positionSeconds, beat.watchedDeltaSeconds);
        return;
      }

      try {
        setProgress(
          await api.recordProgress(lessonId, beat.positionSeconds, beat.watchedDeltaSeconds),
        );
      } catch (error) {
        // A dropped beat is not worth interrupting a lesson over — the next
        // one carries the playhead. An entitlement refusal is different: it
        // means the subscription lapsed mid-lesson, and continuing to play
        // would be showing paid content to somebody who is no longer paying.
        if (error instanceof ApiError && error.entitlementReason) {
          setDenial(error.entitlementReason);
          videoRef.current?.pause();
          playingRef.current = false;
          setPlaying(false);
        }
      }
    },
    [lessonId],
  );

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        // Only the progress. The lesson itself arrived as a prop — see
        // `LessonPlayerProps`.
        const existing = await api.lessonProgress(lessonId);
        if (cancelled) return;

        setProgress(existing);
        if (existing) {
          // Resume. The playhead is restored before anything can play, so a
          // learner never watches the first ten seconds again while the page
          // catches up.
          positionRef.current = existing.last_position_seconds;
          lastSentPositionRef.current = existing.last_position_seconds;
          setPosition(existing.last_position_seconds);
        }
        // Only now may this page report anything.
        readyRef.current = true;

        try {
          const ticket = await api.playbackToken(lessonId);
          if (!cancelled) setPlayback(ticket);
        } catch (error) {
          if (error instanceof ApiError && error.entitlementReason) {
            if (!cancelled) setDenial(error.entitlementReason);
          } else if (!cancelled) {
            // A 409 here means the media is still transcoding. That is not a
            // failure of the page, and the transcript may still be readable.
            setPlayback(null);
          }
        }

        try {
          const transcript = await api.lessonTranscript(lessonId);
          if (!cancelled) {
            setSegments(transcript.segments);
            setCaptions({
              code: transcript.language_code,
              name: transcript.language_name,
            });
          }
        } catch {
          // 404 is ordinary: no approved transcript for this lesson. An
          // unapproved one is indistinguishable from none, by design
          // (ADR-014 §3), and the panel simply does not appear.
        }
      } catch (error) {
        if (cancelled) return;
        setFailure(
          error instanceof ApiError && error.problem.status === 404
            ? "That lesson does not exist."
            : "This lesson could not be loaded.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [lessonId, attempt]);

  /**
   * Restore the remembered speed once, on the client.
   *
   * **`react-hooks/set-state-in-effect` objects to this, and it is wrong here.**
   * The rule's usual advice — a lazy `useState(() => readPlaybackRate())` — reads
   * during render, and this component is server-rendered despite `"use client"`:
   * the lesson route is dynamic, so the server renders it first. There
   * `localStorage` does not exist, the read returns the default, and the client's
   * first render would then return a stored `0.75` against server HTML that said
   * `1` — a hydration mismatch.
   *
   * That is the exact fault M15 spent a day on, where a mismatch left the landing
   * page's hero stuck at `opacity: 0` for every reduced-motion visitor. An effect
   * costs one extra render and cannot mismatch, because it runs after hydration.
   */
  useEffect(() => {
    const stored = readPlaybackRate();
    rateRef.current = stored;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- see above: reading browser storage during render is a hydration mismatch, and this component is server-rendered
    setRate(stored);
  }, []);

  useEffect(() => {
    let secondsSinceBeat = 0;

    const ticker = window.setInterval(() => {
      // Scaled by the rate, because the server measures completion against the
      // lesson's *duration* — see `watchedSince`. Wall-clock counting makes a
      // lesson uncompletable at 1.5× and completable half-heard at 0.5×.
      const watched = watchedSince(1, playingRef.current, rateRef.current);
      unreportedRef.current += watched;

      // The stand-in advances its own clock; a real element is asked for its
      // playhead, because seeking and buffering both move it without us.
      //
      // The stand-in honours the rate too — one line, and it is what makes the
      // control demonstrable before a video provider exists, which is the whole
      // argument for the stand-in existing at all (ADR-016 §4).
      if (playingRef.current && !videoRef.current) {
        positionRef.current += rateRef.current;
        setPosition(positionRef.current);
      } else if (videoRef.current) {
        positionRef.current = videoRef.current.currentTime;
        setPosition(videoRef.current.currentTime);
      }

      secondsSinceBeat += 1;
      if (secondsSinceBeat >= BEAT_SECONDS) {
        secondsSinceBeat = 0;
        void send(false);
      }
    }, 1000);

    // `pagehide`, not `beforeunload`: mobile browsers freeze a backgrounded
    // tab without ever firing `beforeunload`, which is where a phone-shaped
    // audience loses its last stretch of watching.
    const onHide = () => void send(true);
    window.addEventListener("pagehide", onHide);

    return () => {
      window.clearInterval(ticker);
      window.removeEventListener("pagehide", onHide);
      void send(true);
    };
  }, [send]);

  const seek = useCallback((seconds: number) => {
    positionRef.current = seconds;
    setPosition(seconds);
    if (videoRef.current) videoRef.current.currentTime = seconds;
  }, []);

  /**
   * Change the speed, apply it, and remember it.
   *
   * The ref is what the ticker reads — state would be captured as it was on the
   * render that installed the interval, which is the same trap the position and
   * playing refs above exist for.
   */
  const changeRate = useCallback((next: PlaybackRate) => {
    rateRef.current = next;
    setRate(next);
    writePlaybackRate(next);
    if (videoRef.current) videoRef.current.playbackRate = next;
  }, []);

  const togglePlay = useCallback(() => {
    const next = !playingRef.current;
    playingRef.current = next;
    setPlaying(next);
    if (videoRef.current) {
      if (next) void videoRef.current.play();
      else videoRef.current.pause();
    }
  }, []);

  async function markComplete() {
    setCompleting(true);
    try {
      setProgress(await api.markLessonComplete(lessonId));
    } catch (error) {
      if (error instanceof ApiError && error.entitlementReason) {
        setDenial(error.entitlementReason);
      }
    } finally {
      setCompleting(false);
    }
  }

  if (loading) return <p className="text-sm text-ink-subtle">Loading the lesson…</p>;
  if (failure) {
    return (
      <LoadFailure onRetry={retry}>{failure}</LoadFailure>
    );
  }
  if (!lesson) return null;

  const finished = progress?.completed_at != null;

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-6 [overflow-wrap:anywhere]">
        <header className="border-b border-line pb-5">
          <PageTitle variant="section">{lesson.title}</PageTitle>
        </header>

        {denial ? (
          <Notice tone="error" title={refusalFor(denial).title}>
            {refusalFor(denial).detail}
          </Notice>
        ) : null}

        {url ? (
          <video
            ref={videoRef}
            src={url}
            controls
            onPlay={() => {
              playingRef.current = true;
              setPlaying(true);
            }}
            onPause={() => {
              playingRef.current = false;
              setPlaying(false);
            }}
            onLoadedMetadata={() => {
              if (videoRef.current) {
                if (positionRef.current > 0) {
                  videoRef.current.currentTime = positionRef.current;
                }
                // Loading a source resets `playbackRate` to 1, so a remembered
                // speed has to be reapplied here rather than only when it changes.
                videoRef.current.playbackRate = rateRef.current;
              }
            }}
            className="w-full rounded-(--radius-md) bg-black shadow-(--shadow-md)"
          >
            {/*
             * Subtitles come from the same rows the panel renders, as the
             * projection a `<track>` element can consume (invariant 13).
             *
             * **Only when there is a transcript.** It used to render
             * unconditionally, so a lesson without one pointed a caption track at
             * an endpoint that answers 404 — a captions entry the browser offers
             * and which produces nothing when chosen.
             *
             * `srclang` matters beyond tidiness: without it nothing can tell what
             * language the captions are in, which is WCAG 3.1.2 Language of Parts
             * territory once they differ from the page. `label` is what the
             * browser's captions menu shows; without it the learner picks from an
             * unnamed entry. Both come from the payload — never hardcoded, and
             * never inferred from the course, which is what ADR-033 §3 rightly
             * warned against and wrongly concluded was unavoidable.
             */}
            {captions ? (
              <track
                kind="captions"
                src={`/api/v1/lessons/${lessonId}/transcript.vtt`}
                srcLang={captions.code}
                label={captions.name}
                default
              />
            ) : null}
          </video>
        ) : (
          <div className="rounded-(--radius-md) border border-line bg-surface-sunken p-5 sm:p-6">
            <p className="mb-4 max-w-prose text-sm leading-relaxed text-ink-muted">
              No video provider is configured, so this is a stand-in clock. It reports
              progress exactly as a real player would.
            </p>
            <Button variant="secondary" onClick={togglePlay} disabled={denial != null}>
              {playing ? "Pause" : "Play"}
            </Button>
          </div>
        )}

        {/*
         * The two comfort controls, and why they are buttons and a select rather
         * than keyboard shortcuts.
         *
         * Single-character shortcuts — `k`, `j`, `l`, the convention borrowed from
         * video sites — are constrained by **WCAG 2.2 AA 2.1.4 Character Key
         * Shortcuts**, which ADR-030 committed this product to: they must be
         * switchable off, remappable, or active only while the component has focus.
         * Meeting that means a preferences surface and a focus-scoped handler for
         * two actions. Real controls satisfy it by construction, are reachable by
         * Tab, announce themselves, and work on a touch screen, where a keyboard
         * shortcut is nothing at all.
         *
         * Arrow keys and space already work inside the native `<video>` when it has
         * focus. This row is for the two actions its own controls do not offer
         * prominently, and for the stand-in, which has no controls at all.
         */}
        <div role="group" aria-label="Playback controls" className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line pb-5">
          <Button
            variant="secondary"
            onClick={() => seek(replayFrom(positionRef.current))}
            disabled={denial != null}
          >
            {/* The label says what it does, not which direction an icon points.
                "Back 5 seconds" is what a screen reader should read out. */}
            Back {REPLAY_SECONDS} seconds
          </Button>

          <div className="flex items-center gap-2">
            <label htmlFor="playback-rate" className="text-sm text-ink-muted">
              Speed
            </label>
            <select
              id="playback-rate"
              value={rate}
              onChange={(event) => changeRate(Number(event.target.value) as PlaybackRate)}
              disabled={denial != null}
              className="min-h-11 rounded-(--radius-sm) border border-line-strong bg-surface px-3 py-2
                text-base text-ink disabled:opacity-60"
            >
              {PLAYBACK_RATES.map((option) => (
                <option key={option} value={option}>
                  {option}×
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-col items-start gap-4 text-sm text-ink-muted sm:flex-row sm:items-center sm:justify-between">
          <span className="min-w-0 tabular-nums">
            At {timestamp(position)}
            {progress ? ` · ${timestamp(progress.watched_seconds)} watched` : null}
          </span>

          {finished ? (
            <span className="font-medium text-success">Completed</span>
          ) : (
            <Button
              variant="secondary"
              onClick={() => void markComplete()}
              pending={completing}
              disabled={denial != null}
            >
              Mark complete
            </Button>
          )}
        </div>
      </div>

      {segments.length > 0 ? (
        <div className="flex min-w-0 max-h-[32rem] flex-col rounded-(--radius-md) border border-line bg-surface p-5">
          {/* `captions?.code` is the same value the `<track srclang>` carries, so the
              spoken and written transcript cannot disagree about their language. */}
          <TranscriptPanel
            segments={segments}
            positionSeconds={position}
            onSeek={seek}
            languageCode={captions?.code}
          />
        </div>
      ) : null}
    </div>
  );
}
