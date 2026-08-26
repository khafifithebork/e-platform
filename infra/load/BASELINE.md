# Load baseline — public read surface

**Recorded:** 2026-08-26
**Script:** `infra/load/catalogue.js`
**Task:** M12 T7 · **Decision:** ADR-022 §5

---

## Read this before quoting a number from it

**These are not production numbers, and the gap is large enough that treating
them as production numbers would be worse than having none.**

The run was against the **development image** — `docker compose` service `api`,
built at `target: dev`, running with `DEBUG=True` and an autoreloading server,
on Docker Desktop for Windows. Every one of those costs latency, and `DEBUG` in
particular makes Django keep every SQL query it executes in memory for the
lifetime of the request.

What this baseline is good for:

- **Comparison against itself.** Re-run it after a change and the difference is
  real, because everything else was held still.
- **Relative cost between endpoints**, which is the same ordering it would have
  in production even if the absolute numbers are not.

What it is not good for: capacity planning, a p95 target, or an answer to "is
this fast enough". M13 measures a production-shaped deployment.

**No threshold is asserted, deliberately** (ADR-022 §5). §6 forbids inventing
infrastructure facts, and a target written before anything was measured is one.
A threshold derived from a production baseline later is a decision; one written
today would be a guess wearing a decision's clothes.

---

## Conditions

| | |
|---|---|
| Concurrency | 10 virtual users, constant |
| Duration | 60s |
| Catalogue size | 500 published courses, 6 languages (`manage.py seed_catalogue`, fixed seed) |
| Backend | `eplatform-api`, dev target, `DEBUG=True`, uvicorn |
| Database | PostgreSQL 16 in the compose stack |
| Host | Windows 10, Docker Desktop |
| Throttling | **Disabled** for the run — see below |
| k6 | `grafana/k6:latest` via Docker |

### Why throttling was disabled

The public read surface is rate-limited per IP: 120/min for the catalogue,
30/min for search. A load test runs from one host, so with those in force it
measures the throttle rather than the endpoint — every run would report the
same number, which is the limit. Real load arrives from many addresses.

The switch is `DJANGO_DISABLE_THROTTLES_FOR_LOAD_TEST`, and it lives in
`config/settings/local.py` only. Production never loads that module, so a way
to turn throttling off cannot exist there by construction.

---

## Results

Every check passed: **1512 requests, 0 failures, 24.9 req/s.**

| Endpoint | p50 | p95 | p99 | max |
|---|---|---|---|---|
| `catalogue/courses/` | 350ms | 518ms | 591ms | 682ms |
| `catalogue/courses/{slug}/` | 364ms | 550ms | 611ms | 668ms |
| `catalogue/search/?q=` | **419ms** | **712ms** | 816ms | 911ms |
| All requests | 371ms | 649ms | 738ms | 911ms |

### What the shape says

**Search is the most expensive endpoint, by roughly 20% at p50 and 30% at
p95.** That is the ordering M11 predicted when it gave search its own, tighter
throttle scope — a ranked full-text query over a GIN index costs more than a
cursor-paginated list. The prediction is now measured rather than asserted.

**Detail costs about the same as the list**, despite doing four queries to the
list's one — the related-course strip and the curriculum prefetch are cheap
against 500 rows. Worth re-measuring at ten times the catalogue size before
concluding it stays that way.

**The 0% failure rate is the load test's own twin.** A run where every request
404s reports excellent latency; the first attempt at this baseline did exactly
that — 100% of checks failed on a `DisallowedHost` 400 while reporting a
tidy-looking 532ms p50. The status check is what makes the numbers mean
anything.

---

## Reproducing it

```bash
docker compose up -d postgres redis
docker compose run -d --name eplatform-api-load \
  -e DJANGO_DISABLE_THROTTLES_FOR_LOAD_TEST=1 \
  -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api,eplatform-api-load \
  --service-ports api
docker compose exec -T api python manage.py migrate --noinput
docker compose exec -T api python manage.py seed_catalogue --courses 500
docker run --rm --network eplatform_default \
  -v "$PWD/infra/load:/scripts" \
  -e BASE_URL=http://eplatform-api-load:8000 -e VUS=10 -e DURATION=60s \
  grafana/k6:latest run /scripts/catalogue.js
```

Afterwards: `manage.py seed_catalogue --clear` and
`docker rm -f eplatform-api-load`.

The seed uses a fixed random seed, so two runs measure the same catalogue. A
baseline over different data each time is not a baseline.
