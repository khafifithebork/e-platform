"use client";

import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

/**
 * The main nav's links, with a pill that slides to sit behind whichever one
 * the pointer is over.
 *
 * **A client component so `SiteShell` itself does not have to be one.**
 * `usePathname` and hover state both need the browser; extracting just the
 * links here is what keeps the shell a Server Component and the
 * `(marketing)` group's static-rendering invariant untouched — the same
 * reasoning that already put `AuthMenu` in its own client boundary rather
 * than making the whole shell client-rendered.
 *
 * The pill tracks **hover**, not the active route. Highlighting the current
 * page too would need its own always-on pill in addition to the one that
 * follows the pointer — two moving indicators reading as one is more
 * confusing than useful on a nav this short, so `aria-current` marks the
 * active route for anyone who cares which page they're on, and the pill is
 * purely a pointer affordance.
 */
export function NavLinks({ items }: { items: ReadonlyArray<{ href: string; label: string }> }) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <>
      {items.map((item) => {
        const active = pathname === item.href;

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            onMouseEnter={() => setHovered(item.href)}
            onMouseLeave={() => setHovered(null)}
            className="relative px-1 py-1 text-ink-muted transition-colors hover:text-ink"
          >
            {!reduceMotion && hovered === item.href && (
              <motion.span
                layoutId="nav-hover-pill"
                className="absolute inset-x-[-8px] inset-y-[-6px] -z-10 rounded-[--radius-sm]
                  bg-surface-sunken"
                transition={{ type: "spring", stiffness: 500, damping: 35 }}
              />
            )}
            {item.label}
          </Link>
        );
      })}
    </>
  );
}
