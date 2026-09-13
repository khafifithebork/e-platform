interface NoticeProps {
  tone: "error" | "success";
  title?: string;
  children: React.ReactNode;
}

const TONES = {
  error: {
    box: "border-danger/30 bg-danger-subtle text-danger",
    // assertive: an error usually means the thing the user just tried failed,
    // and they should not discover that only when they next tab somewhere.
    live: "assertive" as const,
    symbol: "!",
    badge: "bg-danger/15 text-danger",
  },
  success: {
    box: "border-success/30 bg-success-subtle text-success",
    live: "polite" as const,
    symbol: "✓",
    badge: "bg-success/15 text-success",
  },
};

/**
 * A page-level message.
 *
 * Carries a symbol as well as a colour: colour alone is not an indicator
 * anyone with a colour-vision deficiency can rely on, and the tone here is
 * often the entire content of the response.
 */
export function Notice({ tone, title, children }: NoticeProps) {
  const style = TONES[tone];

  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      aria-live={style.live}
      className={`flex gap-3 rounded-[--radius-md] border px-4 py-3.5 text-sm shadow-[--shadow-sm] ${style.box}`}
    >
      <span
        aria-hidden="true"
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full
          text-xs font-semibold ${style.badge}`}
      >
        {style.symbol}
      </span>
      <div className="flex flex-col gap-1 pt-0.5">
        {title && <p className="font-medium">{title}</p>}
        <div>{children}</div>
      </div>
    </div>
  );
}
