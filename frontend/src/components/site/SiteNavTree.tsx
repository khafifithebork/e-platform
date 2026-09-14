"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { AuthState } from "@/lib/auth/useCurrentUser";
import { useCurrentUser } from "@/lib/auth/useCurrentUser";
import { cn } from "@/lib/utils/cn";

/**
 * A branch-style map of the app's own pages, standing in the margin a fixed
 * shell width otherwise leaves empty.
 *
 * **Lists pages, not the DOM.** The alternative — reflecting the current
 * page's actual heading/landmark structure — is an accessibility-inspector
 * feature, not a navigation aid, and this app already has one skip link and
 * one labelled `<nav>` per landmark; a second tool for inspecting that
 * structure would duplicate what a browser's own accessibility tree already
 * shows. This is the header's link set, redrawn as a tree, plus the one
 * branch the header's `AuthMenu` covers with dynamic content instead of a
 * link: the account section shows the sign-in/register pair or "My courses"
 * for exactly the same reason `AuthMenu` waits for `unknown` to resolve
 * before choosing — see `useCurrentUser`.
 *
 * **Two renderings behind one component**, not two components, so the page
 * data (pathname, auth state) is fetched once and the tree markup — `TreeList`
 * — is written once: a sticky sidebar from `xl` up, and a floating toggle
 * that opens a slide-in panel below it. Below `xl` there is no room beside a
 * `max-w-7xl` page for a permanent column without shrinking the content back
 * to the width this component exists to stop being empty.
 */
export function SiteNavTree() {
  // `usePathname` can return `null` outside a router (Next's own type
  // acknowledges this) — falls back to "/" so `isActive`'s `.startsWith`
  // below has a string to call it on rather than a rendering crash.
  const pathname = usePathname() ?? "/";
  const auth = useCurrentUser();
  const reduceMotion = useReducedMotion();
  const [open, setOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // A followed link should not leave the drawer standing over the page it
  // just navigated to. Adjusted during render rather than in an effect — the
  // pattern React's own docs recommend for "reset state when a prop
  // changes" — so it takes effect in the same render pass instead of
  // flashing the old panel for one frame before an effect can close it.
  const [previousPathname, setPreviousPathname] = useState(pathname);
  if (pathname !== previousPathname) {
    setPreviousPathname(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;

    // Moves focus into the panel on open and back to the toggle on close, so
    // a keyboard user opening this lands somewhere inside it rather than on
    // whatever was next in the background tab order.
    panelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <>
      {/*
       * `bg-surface` reads as a lighter tone than the page's own `bg-paper`
       * in both schemes (surface is the raised-card colour, not a second
       * background invented for this) — that plus the right border is what
       * makes this a column instead of nav links floating in the margin.
       */}
      <nav
        aria-label="Site map"
        className="hidden shrink-0 border-r border-line bg-surface xl:block xl:w-64"
      >
        <div className="sticky top-24 px-6 py-10">
          <TreeList pathname={pathname} auth={auth} />
        </div>
      </nav>

      <button
        ref={toggleRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-controls="site-map-panel"
        className="fixed bottom-5 left-5 z-40 flex items-center gap-2 rounded-full border
          border-line-strong bg-surface px-4 py-2.5 text-sm font-medium text-ink
          shadow-[--shadow-card-hovered] transition-colors hover:border-ink-subtle xl:hidden"
      >
        <span aria-hidden="true" className="font-mono">
          ├─
        </span>
        Site map
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              aria-hidden="true"
              onClick={() => setOpen(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.2 }}
              className="fixed inset-0 z-40 bg-ink/40 xl:hidden"
            />

            <motion.div
              id="site-map-panel"
              ref={panelRef}
              role="dialog"
              aria-modal="true"
              aria-label="Site map"
              tabIndex={-1}
              initial={reduceMotion ? { x: 0 } : { x: "-100%" }}
              animate={{ x: 0 }}
              exit={reduceMotion ? { x: 0 } : { x: "-100%" }}
              transition={{ duration: reduceMotion ? 0 : 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="fixed inset-y-0 left-0 z-50 w-72 max-w-[80vw] overflow-y-auto border-r
                border-line bg-surface p-6 shadow-[--shadow-card-hovered] focus:outline-none xl:hidden"
            >
              <div className="mb-5 flex items-center justify-between">
                <span className="font-display text-xs uppercase tracking-widest text-ink-subtle">
                  Site map
                </span>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close site map"
                  className="rounded-[--radius-sm] p-1 text-ink-subtle transition-colors hover:text-ink"
                >
                  ✕
                </button>
              </div>

              <TreeList pathname={pathname} auth={auth} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

/** True for the page itself, and for anything nested under it (a course's own detail page under "Courses"). */
function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function TreeList({ pathname, auth }: { pathname: string; auth: AuthState }) {
  // Held back until the answer arrives, the same reason `AuthMenu` reserves
  // its own space rather than defaulting to signed-out — showing "Sign in"
  // for a moment to somebody who is signed in reads as having been logged out.
  const accountKnown = auth.status !== "unknown";

  return (
    <ul className="flex flex-col gap-1 text-sm">
      <TreeItem href="/" label="Home" active={isActive(pathname, "/")} />
      <TreeItem href="/courses" label="Courses" active={isActive(pathname, "/courses")} />
      <TreeItem href="/pricing" label="Pricing" active={isActive(pathname, "/pricing")} last={!accountKnown} />

      {accountKnown &&
        (auth.status === "signed-in" ? (
          <TreeBranch label="Account" last>
            <TreeItem href="/my-courses" label="My courses" active={isActive(pathname, "/my-courses")} last />
          </TreeBranch>
        ) : (
          <TreeBranch label="Account" last>
            <TreeItem href="/login" label="Sign in" active={isActive(pathname, "/login")} />
            <TreeItem href="/register" label="Create account" active={isActive(pathname, "/register")} last />
          </TreeBranch>
        ))}
    </ul>
  );
}

function TreeItem({
  href,
  label,
  active,
  last = false,
}: {
  href: string;
  label: string;
  active: boolean;
  last?: boolean;
}) {
  return (
    <li>
      <Link
        href={href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex items-center gap-1.5 rounded-[--radius-sm] py-1 pr-2 transition-colors",
          active ? "font-medium text-accent" : "text-ink-muted hover:text-ink",
        )}
      >
        <span aria-hidden="true" className="font-mono text-ink-subtle">
          {last ? "└─" : "├─"}
        </span>
        {label}
      </Link>
    </li>
  );
}

function TreeBranch({ label, last = false, children }: { label: string; last?: boolean; children: ReactNode }) {
  return (
    <li className="flex flex-col gap-1">
      <span className="flex items-center gap-1.5 py-1 text-ink-subtle">
        <span aria-hidden="true" className="font-mono">
          {last ? "└─" : "├─"}
        </span>
        {label}
      </span>
      <ul className="ml-[3px] flex flex-col gap-1 border-l border-line pl-4">{children}</ul>
    </li>
  );
}
