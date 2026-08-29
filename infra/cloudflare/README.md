# Cloudflare Workers

The Next.js half of B-lite (ADR-025). Django is not here — it runs on a Hetzner
box, and `infra/hetzner/` holds that side.

Configuration lives in `frontend/`, beside the application, because that is
where the adapter expects it: `wrangler.jsonc` and `open-next.config.ts`. This
file is the reasoning around them.

---

## The prerequisite is done

ADR-025 recorded one blocker: `@opennextjs/cloudflare@1.20.4` declares
`peer next@">=15.5.24 <16 || >=16.3.3"`, and this project pinned `16.3.1` —
inside the excluded gap, so `npm install` refused outright.

**Next is now pinned at `16.3.3`**, and the Worker builds:

```
Worker saved in `.open-next/worker.js` 🚀
OpenNext build complete.
```

317 frontend tests, `tsc`, eslint, `npm audit --audit-level=high`,
`verify:static` and `verify:a11y` all pass on the new version. The build output
is 25 MB, dominated by Next's own compiled server runtime.

---

## What was generated, and what was changed

`opennextjs-cloudflare migrate` wrote `wrangler.jsonc`, `open-next.config.ts`,
`public/_headers`, four npm scripts, and appended a line to `next.config.ts`.
Three things were edited afterwards, and the reasons are in the files:

- **The Worker is named `e-platform-web`**, not `frontend`. The generator names
  it after the directory, and `frontend` is not a name anybody wants to see in
  a Cloudflare dashboard beside other projects. The self-reference service
  binding was renamed to match — they must be identical.
- **The `images` binding was removed.** It configures Next's image optimizer
  and **nothing in this application imports `next/image`**. A binding for an
  unused feature is configuration nobody can explain in six months, and on
  Cloudflare it is a billable product.
- **The appended line in `next.config.ts` was documented and moved.** It
  initialises Cloudflare bindings during `next dev`, which is worth keeping —
  without it `next dev` behaves differently from the Worker the same code runs
  in. As generated it was a bare floating promise sitting after
  `export default`, which reads as something pasted in by accident.

---

## The thing that will bite, and it is not obvious

**The API origin is baked into the build.**

`next.config.ts` proxies `/api/*` to Django with an `afterFiles` rewrite —
ADR-001 §2.1's same-origin routing, which is why the session cookie stays
simple. **Next serializes rewrites into the build output.** Read out of the
Worker build produced on this machine:

```json
{ "source": "/api/:path(.*)", "destination": "http://localhost:8000/api/:path" }
```

An absolute URL, fixed at build time. So:

- **`API_ORIGIN` at runtime does nothing.** The destination is already decided.
- **One Worker build cannot serve two environments.** Staging and production
  need separate builds with their own `API_ORIGIN`.
- **A Worker built in CI without `API_ORIGIN` set proxies to `localhost`**,
  which on Cloudflare's edge is nothing at all.

This was found at M15 T9 on the ordinary Next build and is recorded in
`docs/specs/m15-public-catalogue.md` §4.3. It applies identically here, and it
is why the deploy pipeline (M13 T9) must pass the environment's own origin at
build time rather than at run time.

**It is also a live argument for §11 #4.** A Cloudflare Worker owning `/api/*`
at the edge does not have this property at all, because the routing lives in
the Worker rather than in the Next build. That question is still open, and this
is the strongest evidence yet for answering it as path routing.

---

## Still unproven

**The `/api/*` rewrite has never been exercised through a running Worker.**
ADR-025 names this as the one unknown the spike did not close, and it remains
open: the build produces a Worker, it does not prove the proxy behaves.

The check is not that a request arrives. It is that **the session cookie
survives the round trip in both directions** — `Set-Cookie` coming back from
Django, and `Cookie` going out on the next request. Invariant 9 and ADR-001
§2.1 both rest on it, and a same-origin rewrite that drops cookies looks
exactly like a login that silently fails.

```bash
cd frontend
API_ORIGIN=http://localhost:8000 npx opennextjs-cloudflare build
npx wrangler dev            # against `make dev` running Django
# then: sign in through the Worker, and confirm the session survives a reload
```

Perhaps thirty minutes. It should happen before anything is deployed, not after.

**Caching is not configured.** `migrate` says so on the way out:
*"⚠️ Setup cache, see https://opennext.js.org/cloudflare/caching"*. The R2
incremental cache is commented out in `open-next.config.ts`. Every public route
is statically generated (ADR-024), so there is little for an incremental cache
to do today — but that changes the moment anything revalidates, and it is
unexplored rather than decided.

---

## What is still the owner's to do

1. Create the Cloudflare account and enter payment details.
2. `npx wrangler login`, which is an interactive browser authentication.
3. Choose the hostnames, and point DNS at the Worker and at the Hetzner box.
4. Run the cookie check above.

**`npm run deploy` exists and publishes to Cloudflare.** It is deliberately not
wired into CI: M13 T9 is where deploy-on-merge is designed, and a deploy script
that anybody can run by accident before there is an account is worse than one
that has to be typed.

---

## A note on the dependency footprint

The adapter pulled **225 packages**, including `@opennextjs/aws` and AWS SDK
packages beneath it — the Cloudflare adapter is built on the AWS one. That is
not a defect, but `npm audit` runs against all of it in CI (M12 T4), and it is
worth knowing that a transitive advisory in an AWS SDK package can now fail this
project's build. It reports zero vulnerabilities today.
