"use client";

import { ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import Image from "next/image";
import Link from "next/link";

import { buttonStyles } from "@/components/ui/Button";
import { PageTitle } from "@/components/ui/PageTitle";

/** Only the decorative art animates. Text and links work before hydration. */
export function Hero() {
  return (
    <section aria-labelledby="home-title" className="mx-auto grid w-full max-w-7xl gap-4 px-6 pt-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:gap-0 lg:pt-4">
      <div className="relative z-10 flex min-w-0 flex-col items-start gap-6 lg:py-16">
        <PageTitle variant="editorial" id="home-title">
          Language courses, reviewed before they are published.
        </PageTitle>
        <p className="max-w-sm font-serif text-lg leading-snug text-ink">
          Video, audio and written lessons. Transcripts and progress, in one place.
        </p>
        <div className="flex w-full flex-col items-start gap-3 sm:w-auto">
          <Link href="/courses" className={buttonStyles({ variant: "primary", size: "lg", lift: true, className: "w-full gap-5 sm:w-auto" })}>
            Browse the catalogue
            <ArrowRight aria-hidden="true" size={18} strokeWidth={1.5} />
          </Link>
          <Link href="/pricing" className="inline-flex min-h-11 items-center text-accent underline underline-offset-4 hover:text-accent-hover">
            See pricing
          </Link>
        </div>
      </div>
      {/* MotionConfig owns reduced motion without a server/client render branch. */}
      <motion.div
        aria-hidden="true"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
        className="mx-auto w-full max-w-xl lg:max-w-none"
      >
        <Image
          src="/illustrations/learning-scene.webp"
          alt=""
          width={960}
          height={960}
          unoptimized
          loading="eager"
          className="h-auto w-full"
        />
      </motion.div>
    </section>
  );
}
