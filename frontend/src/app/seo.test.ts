/**
 * Canonical URLs, the sitemap and robots.txt — and the state nobody configures.
 *
 * **The interesting case is `SITE_URL` unset**, because that is the state this
 * repository is in and will be in until a domain exists. The fail-safe behaviour
 * agreed with the owner on 2026-09-28 is: no canonical tags, an empty sitemap,
 * `Disallow: /`. The failure mode being guarded against is the *other* default —
 * quietly emitting `http://localhost:3000` canonicals, which de-indexes every page
 * and looks like it worked.
 *
 * Environment variables are set with `vi.stubEnv` per test rather than at module
 * load, which is why `siteUrl()` reads `process.env` on every call instead of
 * caching. That is a small cost paid so this file can test both states at all.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { InvalidSiteUrl, canonical, isIndexable, publicMetadata, siteUrl } from "@/lib/site";

const ORIGIN = "https://lingua.example";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("siteUrl", () => {
  it("is null when nothing is configured", () => {
    vi.stubEnv("SITE_URL", "");
    expect(siteUrl()).toBeNull();
  });

  it("is null for whitespace, which is what an empty compose variable looks like", () => {
    vi.stubEnv("SITE_URL", "   ");
    expect(siteUrl()).toBeNull();
  });

  it("keeps only the origin, so a path or trailing slash cannot double up", () => {
    vi.stubEnv("SITE_URL", "https://lingua.example/some/path/");
    expect(siteUrl()?.toString()).toBe("https://lingua.example/");
  });

  it("throws on a value that is set but unusable, rather than ignoring it", () => {
    /**
     * The asymmetry this whole module turns on: **absence is expected, a typo is
     * not.** Falling back to null for `lingua.example` — no scheme — would treat
     * somebody's mistake as if they had never configured anything, and the symptom
     * would be a silently unindexed site.
     */
    vi.stubEnv("SITE_URL", "lingua.example");
    expect(() => siteUrl()).toThrow(InvalidSiteUrl);

    vi.stubEnv("SITE_URL", "ftp://lingua.example");
    expect(() => siteUrl()).toThrow(/http or https/);
  });

  it("does not put the value in the error message twice over, but does name it", () => {
    // The message has to be actionable in a build log where nobody can inspect
    // state — so it names the offending value and what was expected.
    vi.stubEnv("SITE_URL", "nope");
    expect(() => siteUrl()).toThrow(/"nope"/);
    expect(() => siteUrl()).toThrow(/absolute http\(s\) URL/);
  });
});

describe("isIndexable", () => {
  it("refuses a missing origin", () => {
    expect(isIndexable(null)).toBe(false);
  });

  it("refuses local and test origins, which are valid but never public", () => {
    for (const host of [
      "http://localhost:3000",
      "http://127.0.0.1:3000",
      "http://app.localhost:3000",
      "https://lingua.test",
      "https://lingua.local",
    ]) {
      expect(isIndexable(new URL(host)), host).toBe(false);
    }
  });

  it("accepts a real origin", () => {
    expect(isIndexable(new URL(ORIGIN))).toBe(true);
  });
});

describe("canonical URLs", () => {
  it("are absent, not localhost, when no origin is configured", () => {
    /**
     * **The single most important assertion in this file.** Next's documentation is
     * explicit that a *relative* metadata URL with no `metadataBase` is a build
     * error, so the naive implementation of this fail-safe does not merely emit a
     * wrong URL — it breaks every build. The fields have to be absent.
     */
    vi.stubEnv("SITE_URL", "");

    const meta = publicMetadata({ title: "Courses", description: "d", path: "/courses/" });

    expect(canonical("/courses/")).toBeNull();
    expect(meta.alternates).toBeUndefined();
    expect("alternates" in meta).toBe(false);
    expect(JSON.stringify(meta)).not.toMatch(/localhost/);
  });

  it("are absolute and carry the trailing slash the site serves", () => {
    // `trailingSlash: true` in next.config.ts. A canonical without the slash points
    // at a URL that answers 308, so the tag disagrees with the page serving it.
    vi.stubEnv("SITE_URL", ORIGIN);

    const meta = publicMetadata({ title: "Courses", description: "d", path: "/courses/" });

    expect(meta.alternates?.canonical).toBe("https://lingua.example/courses/");
  });

  it("render the root as the origin itself", () => {
    vi.stubEnv("SITE_URL", ORIGIN);
    expect(publicMetadata({ title: "Lingua", path: "/" }).alternates?.canonical).toBe(
      "https://lingua.example/",
    );
  });

  it("omit an empty description rather than declaring one", () => {
    /**
     * A course with no description in the catalogue — `t8-spanish` today. An empty
     * `<meta description>` is worse than none, and inventing a sentence about a
     * course is §6.
     *
     * **This asserts the object, and the object is not the page.** Next inherits
     * metadata, so the rendered `<meta name="description">` falls back to the root
     * layout's site description — checked in the built HTML, and documented on the
     * course page where somebody reading the code would otherwise conclude the tag
     * is absent. Omitting the key is what lets the fallback happen; emitting `""`
     * would suppress it and ship an empty tag.
     */
    vi.stubEnv("SITE_URL", ORIGIN);

    const meta = publicMetadata({ title: "Spanish", description: "", path: "/courses/spanish/" });

    expect("description" in meta).toBe(false);
  });

  it("sets no `openGraph` or `twitter`, because doing so replaced the inherited ones", () => {
    /**
     * **This is the assertion that would have caught a bug that shipped.**
     *
     * Next merges metadata *shallowly* — its own words are that "duplicate keys are
     * replaced based on their ordering" — so a page setting `openGraph` **replaces**
     * the root layout's whole object rather than merging into it.
     *
     * From PR #96 until 2026-09-30 this helper set
     * `openGraph: { title, description, url }`, which silently stripped
     * `og:site_name` and `og:locale` from all four public pages, and would have
     * stripped `og:image` the moment `opengraph-image.tsx` existed. Found by
     * comparing built HTML: `/login`, which sets no `openGraph`, carried all three;
     * `/`, which used this helper, carried none.
     *
     * Every test written alongside the helper asserted the fields it *set*. None
     * could see what it removed — which is why `assert-page-structure.mjs` now checks
     * `og:image` and `og:site_name` on the assembled HTML as well.
     *
     * The cost of not setting them: `og:url` is not emitted, and `og:title` is the
     * templated form. Both are accepted, and `site.ts` says why.
     */
    vi.stubEnv("SITE_URL", ORIGIN);

    const meta = publicMetadata({ title: "Courses", description: "d", path: "/courses/" });

    expect("openGraph" in meta).toBe(false);
    expect("twitter" in meta).toBe(false);
  });

  it("opt out of the title template only where asked", () => {
    /**
     * The root layout templates child titles as `"%s · Lingua"`. The landing page's
     * title *is* "Lingua", so without `absoluteTitle` it renders "Lingua · Lingua".
     */
    vi.stubEnv("SITE_URL", ORIGIN);

    expect(publicMetadata({ title: "Lingua", path: "/", absoluteTitle: true }).title).toEqual({
      absolute: "Lingua",
    });
    expect(publicMetadata({ title: "Courses", path: "/courses/" }).title).toBe("Courses");
  });
});

describe("the sitemap", () => {
  /** Loaded per test, because the route module reads the environment when called. */
  async function loadSitemap() {
    return (await import("@/app/sitemap")).default;
  }

  it("is empty when no origin is configured, and asks the API for nothing", async () => {
    /**
     * Not merely empty — it must not *fetch*. An empty sitemap that still read the
     * catalogue would stop the build when the API is down, for a file it was about
     * to discard.
     */
    vi.stubEnv("SITE_URL", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(await (await loadSitemap())()).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists the public pages and every published course, with trailing slashes", async () => {
    vi.stubEnv("SITE_URL", ORIGIN);
    vi.doMock("@/lib/catalogue/courses", () => ({
      allPublishedCourses: async () => [{ slug: "spanish" }, { slug: "arabic" }],
    }));

    const urls = (await (await loadSitemap())()).map((entry) => entry.url);

    expect(urls).toEqual([
      "https://lingua.example/",
      "https://lingua.example/courses/",
      "https://lingua.example/pricing/",
      "https://lingua.example/courses/spanish/",
      "https://lingua.example/courses/arabic/",
    ]);
    // Every entry but the root ends in a slash, matching `trailingSlash: true`.
    for (const url of urls) expect(url.endsWith("/")).toBe(true);
  });

  it("declares no lastModified, changeFrequency or priority", async () => {
    /**
     * Deliberate, and worth pinning so it is not "improved" back in. The only date
     * the catalogue exposes is `published_at`, which is not a modification time, and
     * the other two are hints search engines have said for years they ignore. A
     * fabricated weekly cadence is the same class of invention as a fabricated
     * price.
     */
    vi.stubEnv("SITE_URL", ORIGIN);
    vi.doMock("@/lib/catalogue/courses", () => ({
      allPublishedCourses: async () => [{ slug: "spanish" }],
    }));

    for (const entry of await (await loadSitemap())()) {
      expect(Object.keys(entry)).toEqual(["url"]);
    }
  });

  it("encodes a slug the same way the course page's canonical does", async () => {
    // If these two disagreed, a course would advertise one URL in the sitemap and
    // declare a different one as canonical on the page itself.
    vi.stubEnv("SITE_URL", ORIGIN);
    vi.doMock("@/lib/catalogue/courses", () => ({
      allPublishedCourses: async () => [{ slug: "français b1" }],
    }));

    const [fromSitemap] = (await (await loadSitemap())()).slice(-1);
    const fromPage = publicMetadata({
      title: "t",
      path: `/courses/${encodeURIComponent("français b1")}/`,
    }).alternates?.canonical;

    expect(fromSitemap.url).toBe(fromPage);
  });
});

describe("robots.txt", () => {
  async function loadRobots() {
    return (await import("@/app/robots")).default;
  }

  it("disallows everything when no origin is configured", async () => {
    vi.stubEnv("SITE_URL", "");

    const rules = (await loadRobots())();

    expect(rules).toEqual({ rules: { userAgent: "*", disallow: "/" } });
    expect(rules).not.toHaveProperty("sitemap");
  });

  it("disallows everything for a localhost origin", async () => {
    // A locally previewed production build is a real configuration and never a site
    // to invite crawlers to.
    vi.stubEnv("SITE_URL", "http://localhost:3000");

    expect((await loadRobots())()).toEqual({ rules: { userAgent: "*", disallow: "/" } });
  });

  it("points at the sitemap and refuses the private paths for a real origin", async () => {
    vi.stubEnv("SITE_URL", ORIGIN);

    const rules = (await loadRobots())();

    expect(rules.sitemap).toBe("https://lingua.example/sitemap.xml");
    expect(rules.rules).toMatchObject({ userAgent: "*", allow: "/" });
  });

  it("names every private route, because an indexed sign-in form is a lure", async () => {
    /**
     * Not a security control — the session cookie and the server's own checks are
     * that, and a crawler ignoring this file still gets refused. It is about not
     * advertising: a sign-in page in search results is a phishing target wearing our
     * name, and an indexed `/reset-password/` invites arrivals with no token.
     *
     * Asserted as a set against the routes that exist, so a route added later
     * without a decision about indexing shows up here. **It worked**: `/account/`
     * was added on 2026-09-29 and this list is where its absence surfaced.
     */
    vi.stubEnv("SITE_URL", ORIGIN);

    const disallow = (await loadRobots())().rules;
    const listed = Array.isArray(disallow) ? [] : [disallow.disallow].flat();

    for (const path of [
      "/login/",
      "/register/",
      "/forgot-password/",
      "/reset-password/",
      "/verify-email/",
      "/my-courses/",
      "/account/",
      "/api/",
    ]) {
      expect(listed, path).toContain(path);
    }
  });
});

describe("which routes declare a canonical", () => {
  /**
   * **The inheritance trap, pinned.** Next merges metadata down the tree, so an
   * `alternates.canonical` on the root layout becomes every route's canonical
   * unless overridden — `/login` would tell crawlers its real address is `/`, which
   * is the strongest available instruction to treat two pages as one. The root
   * therefore sets `metadataBase` and no canonical, and only public pages carry one.
   */
  const APP = join(process.cwd(), "src", "app");

  it("is the four public pages, and the root layout is not one of them", () => {
    const root = readFileSync(join(APP, "layout.tsx"), "utf8");

    expect(root).toContain("metadataBase");
    // `alternates:` the declaration, not the word — the file explains at length why
    // it has no canonical, and that explanation mentions it.
    expect(root).not.toMatch(/^\s*alternates\s*:/m);
    // `[^}]*` already spans newlines, so no `s` flag — which the tsconfig target
    // predates anyway.
    expect(root).not.toMatch(/openGraph:\s*\{[^}]*\burl\s*:/);
  });

  it("uses the helper on every public page rather than hand-written fields", () => {
    // Hand-written canonicals are how the set above drifts: one page gets a slash
    // wrong, or keeps a relative path, and nothing notices.
    for (const page of [
      join(APP, "(marketing)", "page.tsx"),
      join(APP, "(marketing)", "courses", "page.tsx"),
      join(APP, "(marketing)", "courses", "[slug]", "page.tsx"),
      join(APP, "(marketing)", "pricing", "page.tsx"),
    ]) {
      expect(readFileSync(page, "utf8"), page).toContain("publicMetadata(");
    }
  });

  it("is no auth, learner or instructor route", () => {
    /**
     * These pages are `Disallow`ed in robots.txt and must not contradict that with a
     * canonical inviting indexing. A grep, deliberately: a rendered check on the four
     * routes that exist today would stop enforcing this the moment a fifth appeared.
     *
     * **Matches the declaration and the call, not the names** — and that is a
     * correction, made on 2026-09-29 when `/account` arrived. The first version
     * matched `/alternates|publicMetadata/` anywhere in the file, so it fired on the
     * new page's own docstring saying it has *no* `publicMetadata` and why.
     *
     * That is the second time in two days a grep guard has failed on the comment
     * explaining the thing's absence: the same version of this file asserted the root
     * layout contained no `alternates`, and the root layout explains at length why it
     * does not. **A guard that greps for a name will eventually fire on the prose
     * about that name**, and the fix both times was to match the syntax instead —
     * `alternates:` as a property, `publicMetadata(` as a call.
     */
    const groups = ["(auth)", "(learner)", "(app)", "(instructor)"];
    const offenders: string[] = [];

    for (const group of groups) {
      for (const file of filesUnder(join(APP, group))) {
        if (!file.endsWith(".tsx") && !file.endsWith(".ts")) continue;
        if (file.includes(".test.")) continue;
        if (/alternates\s*:|publicMetadata\s*\(/.test(readFileSync(file, "utf8"))) {
          offenders.push(file);
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});

/** Every file under `dir`, recursively. Returns `[]` for a directory that is absent. */
function filesUnder(dir: string): string[] {
  if (!existsSync(dir)) return [];

  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

describe("the icon", () => {
  /**
   * **The favicon was the Next.js logo until 2026-09-28.** It arrived with the
   * `create-next-app` scaffold in `66c314b` and nothing ever replaced it, so the
   * browser tab wore the framework's brand. `icon.svg` reproduces the header mark
   * `SiteShell` draws with utilities — and because an SVG file cannot read the
   * stylesheet, the values are literals. This is what keeps them honest: a palette
   * change fails here rather than leaving the icon as the last thing in the old
   * colour.
   */
  it("uses the same colours and radius as the header mark", () => {
    const icon = readFileSync(join(process.cwd(), "src", "app", "icon.svg"), "utf8");
    const css = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

    const token = (name: string) =>
      css.match(new RegExp(`^\\s*--${name}:\\s*([^;]+);`, "m"))?.[1]?.trim();

    expect(token("color-accent")).toBeDefined();
    expect(icon).toContain(`fill="${token("color-accent")}"`);
    expect(icon).toContain(`fill="${token("color-brand-coral")}"`);
    expect(icon).toContain(`fill="${token("color-on-accent")}"`);
    expect(icon).toContain(`rx="${token("radius-md")?.replace("px", "")}"`);
  });

  it("shares its brand values with the share cards, which also cannot read the CSS", () => {
    /**
     * `icon.svg` is no longer the only file carrying brand colours as literals.
     * `lib/share/card.ts` does too, because `ImageResponse` renders outside the
     * document — no stylesheet, no `var(--color-accent)`, nothing to inherit.
     *
     * Two files repeating the palette is twice the drift, so the same guard covers
     * both: a palette change fails here rather than leaving the favicon *and* every
     * share card in the old brand colour.
     */
    const card = readFileSync(join(process.cwd(), "src", "lib", "share", "card.ts"), "utf8");
    const css = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

    const token = (name: string) =>
      css.match(new RegExp(`^\\s*--${name}:\\s*([^;]+);`, "m"))?.[1]?.trim();

    for (const [constant, name] of [
      ["CARD_ACCENT", "color-accent"],
      ["CARD_ON_ACCENT", "color-on-accent"],
      ["CARD_PAPER", "color-paper"],
      ["CARD_INK", "color-ink"],
      ["CARD_INK_MUTED", "color-ink-muted"],
      ["CARD_CORAL", "color-brand-coral"],
    ] as const) {
      const value = token(name);
      expect(value, name).toBeDefined();
      expect(card, `${constant} should be ${value}`).toContain(`${constant} = "${value}"`);
    }
  });

  it("is the only icon, and the framework default is gone", () => {
    expect(existsSync(join(process.cwd(), "src", "app", "favicon.ico"))).toBe(false);
  });
});
