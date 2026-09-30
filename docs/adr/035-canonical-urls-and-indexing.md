# ADR-035 — No configured domain, so no claims: canonical URLs, sitemap and robots

**Status:** accepted — the fail-safe was chosen by the owner on 2026-09-28 and
implemented the same day. **One item is left open: setting `SITE_URL`**, which
needs a domain.
**Date:** 2026-09-28
**Decides:** what the public pages tell a crawler when nobody has configured the
site's own address
**Depends on:** ADR-024 (the public catalogue stays static), ADR-025 (hosting:
B-lite — chose the infrastructure, **not a domain**), CLAUDE.md invariant 15, §6
(do not invent facts)

---

## Decision

**With no `SITE_URL`: no canonical tags, an empty sitemap, `Disallow: /`.**

**With a malformed `SITE_URL`: stop the build.**

**With a localhost or `.test` origin: build URLs normally, but still
`Disallow: /`.**

Canonical URLs live on the four public pages only, never on the root layout.

---

## 1. What existed

Nothing. No `sitemap.ts`, no `robots.ts`, no `metadataBase`, no canonical tag on
any page, and no Open Graph beyond a title and description. The favicon was the
**Next.js logo** — it arrived with the `create-next-app` scaffold in `66c314b` on
2026-08-14 and nothing ever replaced it, so every browser tab wore the framework's
brand rather than the product's.

None of that is a bug in the sense of something behaving wrongly. It is a product
that is invisible to a crawler and anonymous in a shared link, which is a different
kind of gap and the reason it sat unnoticed through sixteen milestones.

---

## 2. The real question: what to do with no origin

Every one of these features needs one absolute fact this repository does not have:
**the site's own address.** ADR-025 chose Cloudflare Workers, Hetzner and Neon; it
did not choose a domain, and no environment variable held one.

So the decision is not how to read a variable, it is what to do when it is missing.

| Option | Consequence |
|---|---|
| **Default to `http://localhost:3000`** | The obvious one, and the worst. A deploy that forgot the variable publishes canonical tags telling every crawler that the real address of each page is a machine it cannot reach. That de-indexes the pages **and looks like it worked** — no error, no warning, a sitemap full of plausible-looking URLs |
| **Require it, fail the build** | Honest, and it stops every build in this repository today, for a feature nobody is waiting on |
| **Emit nothing** — *chosen* | No canonical, empty sitemap, `Disallow: /`. Nothing gets indexed, which is **recoverable the moment a domain exists**. Wrong URLs getting indexed is not |

**Not indexed is a recoverable state; wrongly indexed is not.** That is the whole
argument, and it is why the fail-safe is silence rather than a guess.

### A typo is not an absence

`SITE_URL=lingua.example`, with no scheme, **throws and stops the build.**

Treating it as unset would be the same fallback dressed as robustness: somebody was
configuring this and got it wrong, and the symptom of swallowing it is a silently
unindexed site — exactly the outcome the decision above exists to avoid. An absence
is the expected state; a malformed value is a mistake that needs reporting.

### A localhost origin is valid and never indexable

`isIndexable()` is deliberately separate from `siteUrl()`, because "can I build a
URL from this" and "should I invite crawlers" are different questions. A developer
previewing a production build has a perfectly valid origin and must not be able to
invite indexing with it. `localhost`, `127.0.0.1`, `*.localhost`, `*.test` and
`*.local` all build URLs and all get `Disallow: /`.

---

## 3. What Next's documentation decided for us

The first implementation used **relative** paths — `alternates: { canonical: "/courses/" }` —
and let Next resolve them against `metadataBase`, on the assumption that a missing
base would simply emit nothing.

It does not. From `generate-metadata.md`, verbatim:

> "Using a relative path in a URL-based metadata field without configuring a
> metadataBase will cause a build error."

So the naive version of this fail-safe does not emit a wrong URL — **it breaks every
build this repository does today**, because unset is the current state. The fields
are therefore built absolute when there is an origin and omitted entirely when there
is not, rather than delegating the question to the framework.

Worth recording because it is not intuitive, and because the failure would have
arrived as a confusing build error in CI rather than as anything resembling its
cause.

---

## 4. Why the root layout has no canonical

Next merges metadata down the route tree. A canonical on the root layout therefore
becomes **every** route's canonical unless that route overrides it — so `/login`
would carry `<link rel="canonical" href="https://…/">`, which is the strongest
available instruction to a search engine that two different pages are the same page.

The root sets `metadataBase` and nothing URL-shaped. Canonicals come from
`publicMetadata()` in `src/lib/site.ts`, called by exactly four pages, and
`seo.test.ts` greps the `(auth)`, `(learner)`, `(app)` and `(instructor)` groups to
assert none of them has grown one. A rendered check on today's four routes would
stop enforcing that the moment a fifth appeared; the grep does not.

`openGraph.url` is left off the root for the same reason.

---

## 5. What is deliberately absent

| Left out | Why |
|---|---|
| **`lastModified`, `changeFrequency`, `priority`** | The only date the catalogue exposes is `published_at`, which is not a modification time. The other two are hints search engines have said for years they ignore. Inventing a weekly cadence for a curated catalogue is the same class of fabrication as inventing a price (§6), and a test pins their absence so they are not "improved" back in |
| ~~**An Open Graph image**~~ | **Done 2026-09-30.** `next/og` at build time, which ships with Next and stays static — plus a per-course card, which is the one people actually share. `twitter.card` is now `summary_large_image`. See §6a |
| ~~**An `apple-icon`**~~ | **Done 2026-09-30.** The constraint was authoring a raster asset by hand; `ImageResponse` generates the 180×180 PNG at build time from the same brand values, with nothing new installed. See §6a |
| **`favicon.ico`** | Deleted. It was the framework's logo, verified unchanged since the scaffold commit, and it would still have been served at `/favicon.ico` alongside the new `icon.svg` — crawlers and link aggregators fetch that path directly. SVG-only is a deliberate trade against very old browsers |
| **Terms, Privacy, an imprint** | **Not written, and not stubbed.** Real terms, a real data-protection statement and, for EU learners, a real controller identity. An empty privacy page reads as a compliance claim nobody has made. The owner declined stub routes on 2026-09-28; the footer therefore links only to pages that exist |

---

## 6a. The share images, and a regression this ADR's own helper had shipped — **2026-09-30**

§5 left the Open Graph image and the `apple-icon` out on the grounds that generating
one "needs a decision" and that "authoring raster assets is not something to
improvise". **`next/og` answers both at once**: it ships with Next — no `satori` or
`resvg` in `package.json`, so §5 of CLAUDE.md is clear — and Next's documentation says
an `opengraph-image` route is statically optimized unless it uses a request-time API,
so invariant 15 holds. Three routes, three PNGs, all prerendered, one of them per
published course.

### What building them exposed

**`publicMetadata` — added by this ADR — had been stripping `og:site_name` and
`og:locale` from all four public pages since it shipped.**

Next merges metadata *shallowly*. Its own words: "duplicate keys are **replaced**
based on their ordering". So a page that sets `openGraph` replaces the root layout's
entire object rather than merging into it, and this helper set
`openGraph: { title, description, url }`.

Today it would also have discarded the `og:image` the new file convention
contributes — **three of the four cards would simply not have appeared**, and the one
that did (the course page) works only because its image is colocated in the same
segment, where file-based metadata outranks the object.

Found by comparing built HTML, not by reasoning: `/login`, which sets no `openGraph`
at all, carried `og:site_name`, `og:locale` and `og:image`. `/`, which used the
helper, carried none of the three.

**This is the same trap §4 documents, arrived at from the other side.** §4 explains
why the root layout must *not* set a canonical — because inheritance would spread it
to every route. The mirror image, that a *page* setting a key destroys what it
inherited, was not written down, and the helper written in the same change fell into
it.

### The fix, and what it costs

The helper now sets neither `openGraph` nor `twitter`. Everything is inherited, and
Next derives `og:title` and `og:description` from the resolved title and description
— which is where `/login`'s tags came from all along.

Stated rather than discovered: **`og:url` is no longer emitted**, and `og:title` is
now the templated form, "Courses · Lingua" rather than "Courses". `og:url` duplicates
the `<link rel="canonical">` that crawlers actually use, and a site name appearing
twice on a card is a smaller fault than a card with no image.

### Why no test could see it

**Every test written with the helper asserted the fields it set.** The fault was in
what the object *removed*, which is invisible to anything reading that object — and
invisible to a component test, because metadata is assembled by the framework.

So `scripts/assert-page-structure.mjs` now checks `og:image` and `og:site_name` on the
**built HTML** of every public page. It matches pages by shape rather than by slug —
pinning `courses/t8-spanish.html` would tie the check to seeded data, and the day that
seed changed the check would match nothing and report success — and it fails if it saw
fewer than four public pages, which is the guard on the guard. Both halves provoked:
reinstating the override fails it on six counts, and breaking the matcher fails it on
the floor.

### Two other things worth recording

**`verify:static` refused the course image route** until it declared
`dynamicParams = false`. Without it the route prerenders the known slugs *and* keeps a
dynamic fallback, which makes it server-rendered under `(marketing)` — invariant 15 —
and the build reports success either way. An image route is a separate route handler
and does not inherit the page's declaration.

**The cards render in the wrong font, knowingly.** This application ships no web fonts
and uses a system stack deliberately; Satori, which `ImageResponse` runs on, cannot
see system fonts. Fixing it means committing a font file to serve one image, or the
site adopting a web font — both larger than the problem. `lib/share/card.ts` says so,
and `seo.test.ts` guards its colour literals against the tokens, the same way
`icon.svg`'s are guarded and for the same reason: there is no stylesheet inside an
`ImageResponse`.

---

## Consequences

**Positive.** The public pages are describable to a crawler and to a link preview
the day a domain exists, with one environment variable and no code change. The
favicon is the product's. `robots.txt` also stops advertising the authentication
routes — a sign-in form in search results is a phishing lure wearing our name, and
an indexed `/reset-password/` invites arrivals with no token.

**Negative.** Until `SITE_URL` is set the site is deliberately unindexed, and that
is a real cost being accepted on purpose. Anyone who deploys expecting Google to
find the site will find it does not, and the reason is one line in `.env.example` —
which is why that comment is long.

**Security.** `robots.txt` is not a control and the file says so: the session
cookie and the server's own checks are what protect those routes, and a crawler
ignoring the file still gets refused. This is about not advertising.

**Performance.** Nothing measurable. Two more prerendered files; both are static.

**Accessibility.** None. No rendered output changed on any page.

---

## Verification criteria

1. **Done.** 13 provocations, one per property, each confirmed to fail the test that
   protects it — including defaulting the origin to localhost, swallowing a
   malformed value, dropping the trailing slashes, putting a canonical on the root
   layout, and leaving the icon on an old brand colour.
2. **Done, against built output rather than reasoning.** With
   `SITE_URL=https://lingua.example`: four canonical tags, a four-entry sitemap,
   `Host` and `Sitemap` lines in `robots.txt`. With it unset: **zero** canonical
   tags anywhere, an empty `<urlset>`, `Disallow: /`, and no occurrence of
   `localhost` in any built page.
3. **Done.** `npm test` — 44 files, 522 tests. `tsc`, `eslint` and all three
   `verify:*` scripts clean.
4. **Outstanding, needs the owner:** set `SITE_URL`. That needs a domain, and until
   then the fail-safe is the intended behaviour, not a gap.
5. **Outstanding:** the Open Graph image decision, and whether a course with an
   empty description should get a composed one — see below.

## What the build corrected

**A course with an empty description does not ship no description.** The helper
omits the key, and Next then inherits the root layout's site description — so
`t8-spanish`, whose `description` is `""` today, renders "Curated language courses,
reviewed before publication…" as its own `<meta name="description">` and
`og:description`.

Found by reading the built HTML, not by reasoning about the code, which reads as if
the tag were absent. The behaviour is acceptable — the sentence is true of the site
and says nothing false about the course — and it is now documented where it happens
rather than implied away. The alternative worth considering later is composing one
from facts the API does have (title, level, language), which is composition rather
than invention; the third option, making something up, is §6.

## Related

ADR-024, ADR-025, CLAUDE.md invariant 15 and §6,
`docs/specs/frontend-state-and-api.md`, `frontend/.env.example`.
