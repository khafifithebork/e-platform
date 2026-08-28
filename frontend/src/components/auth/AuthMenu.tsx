"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, api, type Me } from "@/lib/api/client";

/**
 * Who you are, and a way out.
 *
 * **The one personalised thing on an otherwise static page.** Invariant 15
 * keeps the `(marketing)` group statically generated, so its HTML is identical
 * for everyone — this resolves in the browser afterwards, the same shape M15's
 * search uses and for the same reason.
 *
 * **Three states, and the first one matters most.** It starts *unknown*:
 * neither "Sign in" nor a name. The obvious alternative is to render the
 * signed-out state as a placeholder, which flashes "Sign in" at somebody who is
 * signed in — and reads as having been logged out, on every page load, for
 * every subscriber. A brief blank is a better lie than a wrong one.
 *
 * The space is reserved while unknown so the header does not shift when the
 * answer arrives. A layout jump in a fixed header is felt on every navigation.
 */
type AuthState = { status: "unknown" } | { status: "anonymous" } | { status: "signed-in"; me: Me };

export function AuthMenu() {
  const [state, setState] = useState<AuthState>({ status: "unknown" });
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    let current = true;

    api
      .me()
      .then((me) => {
        if (current) setState({ status: "signed-in", me });
      })
      .catch((error: unknown) => {
        if (!current) return;

        // **A 403 here is the answer, not a failure.** `/auth/me/` refuses an
        // anonymous request, which is exactly how this component learns nobody
        // is signed in. Treating it as an error would leave the header stuck
        // in its unknown state for every signed-out visitor — which is most of
        // them, on a public catalogue.
        //
        // Anything else — the API being down, a network failure — also lands
        // here, and also resolves to anonymous. That is deliberate: a header
        // that cannot tell you who you are should offer you the way in, not an
        // error message about a request you did not make.
        setState({ status: "anonymous" });
        if (!(error instanceof ApiError)) {
          // Logged rather than shown. Worth finding in a console; not worth a
          // banner on a page the visitor came to read.
          console.debug("Could not resolve the session", error);
        }
      });

    return () => {
      current = false;
    };
  }, []);

  async function signOut() {
    setSigningOut(true);
    try {
      await api.logout();
    } catch (error: unknown) {
      // Caught, not merely passed through a `finally`.
      //
      // This is an async click handler, so nothing awaits its promise: letting
      // the rejection escape produces an unhandled rejection in the console on
      // every failed sign-out. Found because the test for "leaves even when
      // the logout request fails" printed one while passing.
      //
      // Swallowed rather than shown. The navigation below is what the visitor
      // asked for and it happens either way; a message about a request they
      // did not make would arrive on a page they are leaving.
      console.debug("Sign-out request failed; leaving anyway", error);
    } finally {
      /**
       * A full navigation, not `router.refresh()` or a client-side push.
       *
       * **Refreshing does not clear client component state**, and by the time
       * somebody signs out this application may be holding their enrolments,
       * their progress and a lesson body in memory. A soft navigation leaves
       * all of it there for whoever uses the browser next — which on a shared
       * or public machine is the entire point of pressing the button.
       *
       * Next's lint rule says to use `useRouter().push()` for internal
       * navigation, and it is right in general and wrong here: a soft push
       * keeps the JS context alive, which is precisely what must not survive
       * somebody signing out. The rule is suppressed at the call site with a
       * pointer back to this paragraph, so the next person to see the warning
       * finds the reason rather than "fixing" it.
       *
       * Home rather than staying put, because every authed page becomes a 403
       * the moment the cookie is gone, and landing on a refusal after signing
       * out reads as an error rather than as success.
       *
       * In `finally`, so a failed logout request still ends the session from
       * the browser's point of view. If the cookie survived server-side the
       * next request re-establishes the truth; leaving the header signed in
       * after somebody asked to leave is the worse of the two wrongs.
       */
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- see above: a soft navigation would not tear down the JS context, which is the point
      window.location.assign("/");
    }
  }

  if (state.status === "unknown") {
    // `aria-hidden` and no focusable content: a screen reader should not
    // announce an empty region, and a keyboard user should not tab into
    // nothing. It reserves width so the header does not jump.
    return <span aria-hidden="true" className="inline-block w-24" />;
  }

  if (state.status === "anonymous") {
    return (
      <Link
        href="/login"
        className="rounded-[--radius-sm] border border-line-strong px-3 py-1.5
          text-ink hover:border-ink-subtle"
      >
        Sign in
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-4">
      <Link href="/my-courses" className="text-ink-muted hover:text-ink">
        My courses
      </Link>

      {/*
       * The email is the only name this product has — `StudentProfile` may hold
       * a display name, but it is optional and the API documents it as empty
       * when unset. Showing the email is honest and unambiguous; showing an
       * empty string would be a header that forgot who you are.
       */}
      <span className="hidden text-ink-subtle sm:inline" title={state.me.email}>
        {state.me.email}
      </span>

      <button
        type="button"
        onClick={signOut}
        disabled={signingOut}
        className="rounded-[--radius-sm] border border-line-strong px-3 py-1.5
          text-ink hover:border-ink-subtle disabled:opacity-60"
      >
        {signingOut ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
