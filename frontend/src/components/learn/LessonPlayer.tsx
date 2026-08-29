"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
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
  lessonId: string;
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
export function LessonPlayer({ lessonId }: LessonPlayerProps) {
  const [lesson, setLesson] = useState<GatedLesson | null>(null);
  const [progress, setProgress] = useState<LessonProgress | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [playback, setPlayback] = useState<PlaybackToken | null>(null);
  const [denial, setDenial] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);

  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);

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

      const beat = {
        positionSeconds: positionRef.current,
        watchedDeltaSeconds: unreportedRef.current,
      };
      if (!worthSending(beat, lastSentPositionRef.current)) return;

      // Cleared before the request, not after. A beat that fails has still
      // consumed that stretch of watching; carrying it forward would let a
      // flaky connection accumulate an hour and then claim it all at once.
      unreportedRef.current = 0;
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
        const [detail, existing] = await Promise.all([
          api.lesson(lessonId),
          api.lessonProgress(lessonId),
        ]);
        if (cancelled) return;

        setLesson(detail);
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
          if (!cancelled) setSegments(transcript.segments);
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
  }, [lessonId]);

  useEffect(() => {
    let secondsSinceBeat = 0;

    const ticker = window.setInterval(() => {
      const watched = watchedSince(1, playingRef.current);
      unreportedRef.current += watched;

      // The stand-in advances its own clock; a real element is asked for its
      // playhead, because seeking and buffering both move it without us.
      if (playingRef.current && !videoRef.current) {
        positionRef.current += 1;
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
  if (failure) return <Notice tone="error">{failure}</Notice>;
  if (!lesson) return null;

  const finished = progress?.completed_at != null;

  return (
    <div className="grid gap-8 lg:grid-cols-[3fr_2fr]">
      <div className="space-y-4">
        <header>
          <h1 className="font-display text-2xl text-ink">{lesson.title}</h1>
          <p className="text-sm text-ink-subtle">{lesson.course_slug}</p>
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
              if (positionRef.current > 0 && videoRef.current) {
                videoRef.current.currentTime = positionRef.current;
              }
            }}
            className="w-full rounded-[--radius-md] bg-black"
          >
            {/* Subtitles come from the same rows the panel renders, as the
                projection a `<track>` element can consume (invariant 13). */}
            <track kind="captions" src={`/api/v1/lessons/${lessonId}/transcript.vtt`} default />
          </video>
        ) : (
          <div className="rounded-[--radius-md] border border-line bg-surface-sunken p-6">
            <p className="mb-3 text-sm text-ink-muted">
              No video provider is configured, so this is a stand-in clock. It reports
              progress exactly as a real player would.
            </p>
            <Button variant="secondary" onClick={togglePlay} disabled={denial != null}>
              {playing ? "Pause" : "Play"}
            </Button>
          </div>
        )}

        <div className="flex items-center justify-between text-sm text-ink-muted">
          <span>
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
        <div className="max-h-[32rem] rounded-[--radius-md] border border-line bg-surface p-4">
          <TranscriptPanel segments={segments} positionSeconds={position} onSeek={seek} />
        </div>
      ) : null}
    </div>
  );
}
