import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { codeOnly, sourceFilesIn } from "@/test/source";

import { ingestOriginFromDsn } from "./dsn";
import { REDACTED, redactAddresses } from "./redact";

const FRONTEND_ROOT = join(import.meta.dirname, "..", "..", "..");

describe("the ingest origin the CSP has to allow", () => {
  it("is the DSN's scheme and host", () => {
    expect(ingestOriginFromDsn("https://abc123@o44.ingest.de.sentry.io/12")).toBe(
      "https://o44.ingest.de.sentry.io",
    );
  });

  it("keeps a port, because a self-hosted relay has one", () => {
    expect(ingestOriginFromDsn("https://k@relay.example.com:9000/1")).toBe(
      "https://relay.example.com:9000",
    );
  });

  it("carries no key, project or path into the policy", () => {
    const origin = ingestOriginFromDsn("https://abc123@o44.ingest.de.sentry.io/12");

    expect(origin).not.toContain("abc123");
    expect(origin.endsWith("sentry.io")).toBe(true);
  });

  it.each([
    ["undefined", undefined],
    ["empty", ""],
    ["not a URL at all", "obviously-not-a-dsn"],
    ["a non-http scheme", "file:///etc/passwd"],
  ])("returns nothing for %s", (_label, dsn) => {
    expect(ingestOriginFromDsn(dsn)).toBe("");
  });
});

describe("addresses are removed before anything is sent", () => {
  it("removes one from an error message", () => {
    expect(redactAddresses("could not enrol alice@example.com")).toBe(
      `could not enrol ${REDACTED}`,
    );
  });

  it("reaches into nested structures", () => {
    expect(redactAddresses({ extra: { tried: ["retry", "eve@mail.org"] } })).toEqual({
      extra: { tried: ["retry", REDACTED] },
    });
  });

  it("leaves text that is not an address alone", () => {
    // The twin, and the one that matters: a function redacting everything
    // would pass both tests above and quietly ruin every stack trace.
    for (const untouched of ["src/lib/api/client.ts", "5 > 3 and a@b", "@decorator"]) {
      expect(redactAddresses(untouched)).toBe(untouched);
    }
  });

  it("stops descending past its limit, and this is what that costs", () => {
    // Deliberate: an address buried deeper than the cap survives. The
    // alternative is throwing inside `beforeSend`, which drops the whole event.
    let buried: unknown = "leaf@example.com";
    for (let i = 0; i < 12; i += 1) buried = { next: buried };

    expect(JSON.stringify(redactAddresses(buried))).toContain("leaf@example.com");
  });

  it("survives a pathologically deep event", () => {
    let deep: unknown = "leaf@example.com";
    for (let i = 0; i < 2000; i += 1) deep = { next: deep };

    expect(() => redactAddresses(deep)).not.toThrow();
  });
});

describe("the ingest origin reaches the policy", () => {
  // Without this the tests above pass while nothing uses the function. That is
  // the exact failure this repository has shipped four times, and the backend
  // half of M14 T5 caught the same shape in its own scrubber.
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  async function policy(): Promise<string> {
    const { default: config } = await import("../../../next.config");
    const headers = await config.headers!();
    const csp = headers[0].headers.find((header) =>
      header.key.startsWith("Content-Security-Policy"),
    );
    return csp!.value;
  }

  it("adds the DSN's host to connect-src", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://k@o44.ingest.de.sentry.io/12");

    expect(await policy()).toContain("connect-src 'self' https://o44.ingest.de.sentry.io");
  });

  it("adds nothing when there is no DSN", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");

    expect(await policy()).toContain("connect-src 'self';");
  });

  it("still refuses everything else", async () => {
    // A widened connect-src must not have widened the rest of the policy.
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://k@o44.ingest.de.sentry.io/12");
    const csp = await policy();

    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});

describe("the vendor SDK is named in one module", () => {
  const SEAM = join("src", "lib", "observability", "sentry.ts");

  function namesTheVendor(path: string): boolean {
    return /from\s+["']@sentry\/|require\(["']@sentry\//.test(
      codeOnly(readFileSync(path, "utf8")),
    );
  }

  function everySourceFile(): string[] {
    const rootFiles = readdirSync(FRONTEND_ROOT)
      .filter((entry) => /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry))
      .map((entry) => join(FRONTEND_ROOT, entry));
    return [...sourceFilesIn(join(FRONTEND_ROOT, "src")), ...rootFiles];
  }

  it("is imported by exactly one file", () => {
    // Next loads `instrumentation.ts` and `instrumentation-client.ts` in
    // different runtimes, and the tempting shape is a `Sentry.init` in each.
    // Two initialisations drift, and the half that drifts is the browser —
    // where the options that matter are the privacy ones.
    const importers = everySourceFile()
      .filter(namesTheVendor)
      .map((path) => path.slice(FRONTEND_ROOT.length + 1));

    expect(importers).toEqual([SEAM]);
  });

  it("would catch a second importer", () => {
    // The twin. A detector matching nothing passes the test above only because
    // that one asserts an exact list; this checks it detects a real import,
    // and that a comment mentioning one does not count.
    expect(namesTheVendor(join(FRONTEND_ROOT, SEAM))).toBe(true);
    expect(everySourceFile().length).toBeGreaterThan(10);
  });
});
