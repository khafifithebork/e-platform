import Image from "next/image";
import Link from "next/link";

/**
 * One Illustrated Journal shell for every account step.
 *
 * The forms own their client state. This shared presentation needs no pathname
 * lookup or entrance animation, so it can remain a Server Component and show
 * controls immediately. Artwork follows all form content on smaller screens.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div data-site-style="editorial" className="min-h-dvh bg-paper text-ink">
      <div className="mx-auto grid min-h-dvh max-w-7xl lg:grid-cols-2">
        <main className="flex min-w-0 flex-col px-6 py-8 sm:px-12 lg:px-16 lg:py-10">
          <Link
            href="/"
            className="w-fit font-display text-3xl font-bold tracking-tight text-ink hover:text-accent"
          >
            Lingua
          </Link>
          <div className="flex flex-1 items-center py-12 lg:py-16">
            <div className="mx-auto w-full min-w-0 max-w-sm [overflow-wrap:anywhere]">
              {children}
            </div>
          </div>
          <footer className="text-sm text-ink-subtle">
            <Link href="/" className="underline decoration-line-strong underline-offset-4 hover:text-ink">
              Back to the catalogue
            </Link>
          </footer>
        </main>
        <aside
          aria-hidden="true"
          className="flex min-w-0 flex-col items-center justify-center gap-6 px-6 pb-8 sm:px-12 lg:px-4 lg:py-12"
        >
          <Image
            src="/illustrations/sign-in-scene.webp"
            alt=""
            width={960}
            height={960}
            unoptimized
            loading="eager"
            className="h-auto w-full max-w-64 sm:max-w-xs lg:max-w-none"
          />
          <span aria-hidden="true" className="ink-spots w-20 self-end lg:me-12 lg:w-28" />
        </aside>
      </div>
    </div>
  );
}
