"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { BookOpen, CircleUserRound, House, Menu, Wallet, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { AuthState } from "@/lib/auth/useCurrentUser";
import { useCurrentUser } from "@/lib/auth/useCurrentUser";
import { cn } from "@/lib/utils/cn";

/** Shared route list for the desktop rail and mobile drawer. Account links
 * wait for the session response so subscribers never flash a sign-in prompt.
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
    const toggle = toggleRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onResize() {
      // Match the xl rail: a hidden mobile panel must not keep scrolling locked.
      if (window.innerWidth >= 1280) setOpen(false);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
      if (event.key === "Tab") {
        const panel = panelRef.current;
        // Preserve DOM order when filtering different kinds of controls.
        const controls = Array.from(panel?.querySelectorAll<HTMLElement>("*") ?? [])
          .filter((element) => element.matches("a[href], button:not(:disabled)"));
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", onResize);
      document.body.style.overflow = previousOverflow;
      toggle?.focus();
    };
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
        <div className="sticky top-24 px-5 py-8">
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
          shadow-(--shadow-card-hovered) transition-colors hover:border-ink-subtle xl:hidden"
      >
        <Menu aria-hidden="true" size={18} />
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
                border-line bg-surface p-6 shadow-(--shadow-card-hovered) focus:outline-hidden xl:hidden"
            >
              <div className="mb-5 flex items-center justify-between">
                <span className="font-display text-lg font-semibold text-ink">
                  Site map
                </span>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close site map"
                  className="rounded-(--radius-sm) p-3 text-ink-muted transition-colors hover:text-ink"
                >
                  <X aria-hidden="true" size={20} />
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
      <TreeItem href="/pricing" label="Pricing" active={isActive(pathname, "/pricing")} />

      {accountKnown &&
        (auth.status === "signed-in" ? (
          <TreeBranch label="Account">
            <TreeItem href="/my-courses" label="My courses" active={isActive(pathname, "/my-courses")} />
          </TreeBranch>
        ) : (
          <TreeBranch label="Account">
            <TreeItem href="/login" label="Sign in" active={isActive(pathname, "/login")} />
            <TreeItem href="/register" label="Create account" active={isActive(pathname, "/register")} />
          </TreeBranch>
        ))}
    </ul>
  );
}

function TreeItem({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <li>
      <Link
        href={href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex min-h-12 items-center gap-3 rounded-(--radius-md) px-4 py-3 transition-colors",
          active ? "bg-accent-subtle font-semibold text-accent" : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
        )}
      >
        {href === "/" ? <House aria-hidden="true" size={19} /> :
          href === "/pricing" ? <Wallet aria-hidden="true" size={19} /> :
          href === "/courses" || href === "/my-courses" ? <BookOpen aria-hidden="true" size={19} /> :
          <CircleUserRound aria-hidden="true" size={19} />}
        {label}
      </Link>
    </li>
  );
}

function TreeBranch({ label, children }: { label: string; children: ReactNode }) {
  return (
    <li className="mt-6 flex flex-col gap-2 border-t border-line pt-6">
      <span className="px-4 text-sm font-medium text-ink-muted">{label}</span>
      <ul className="flex flex-col gap-1">{children}</ul>
    </li>
  );
}
