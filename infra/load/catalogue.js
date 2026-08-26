// Load baseline for the public read surface. M12 T7, ADR-022 §5.
//
// **This records a baseline. It asserts no threshold.** §6 forbids inventing
// infrastructure facts, and "p95 under 200ms" written before anything was
// measured is exactly that — a number a later milestone would either meet by
// accident or tune towards without knowing whether it mattered. What this
// produces is p50, p95 and an error rate at a stated concurrency on stated
// hardware. A threshold derived from that later is a decision; a threshold
// invented now is a guess wearing a decision's clothes.
//
// The one check present is `status is 200`, and it is not a performance
// threshold — it is the twin. A run where every request 404s would otherwise
// report excellent latency, and that is precisely the shape of a load test
// that proves nothing.
//
// Three endpoints, chosen because they cost different things:
//
//   - `catalogue`  cursor-paginated list. The cheapest, and the one
//                  architecture.md:1054 actually names.
//   - `detail`     one course plus its curriculum plus the related strip —
//                  four queries, one of them M11's ranked neighbour lookup.
//   - `search`     ranked full text over a GIN index. The most expensive thing
//                  an anonymous visitor can ask this service to do, which is
//                  why M11 gave it its own throttle scope. The objective
//                  predates it; measuring the catalogue without it would
//                  measure the cheap half.
//
// The player endpoint is deliberately absent. It mints a signed token behind
// the entitlement resolver, so loading it means either bypassing the resolver —
// measuring something the product does not do — or minting thousands of real
// tokens. M13, against a deployment that can be measured properly.

import http from "k6/http";
import { check, group } from "k6";
import { Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://api:8000";

// Seeded by `manage.py seed_catalogue`, which uses a fixed random seed so two
// runs measure the same catalogue. A baseline over different data each time is
// not a baseline.
const SEARCH_TERMS = ["spanish", "grammar", "conversation", "travel", "beginners"];

const catalogueLatency = new Trend("latency_catalogue", true);
const detailLatency = new Trend("latency_detail", true);
const searchLatency = new Trend("latency_search", true);

export const options = {
  scenarios: {
    baseline: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || "30s",
    },
  },
  // Thresholds deliberately absent — see the header comment. `summaryTrendStats`
  // is set so the recorded numbers include the percentiles the baseline is
  // written down as.
  summaryTrendStats: ["avg", "min", "med", "p(95)", "p(99)", "max"],
};

export default function () {
  group("catalogue", () => {
    const response = http.get(`${BASE}/api/v1/catalogue/courses/`);
    catalogueLatency.add(response.timings.duration);
    check(response, { "catalogue is 200": (r) => r.status === 200 });
  });

  group("detail", () => {
    // A fixed slug from the seeded range. Varying it would measure cache
    // behaviour we have not built yet rather than the query.
    const response = http.get(`${BASE}/api/v1/catalogue/courses/loadtest-42/`);
    detailLatency.add(response.timings.duration);
    check(response, { "detail is 200": (r) => r.status === 200 });
  });

  group("search", () => {
    const term = SEARCH_TERMS[Math.floor(Math.random() * SEARCH_TERMS.length)];
    const response = http.get(
      `${BASE}/api/v1/catalogue/search/?q=${encodeURIComponent(term)}`,
    );
    searchLatency.add(response.timings.duration);
    check(response, { "search is 200": (r) => r.status === 200 });
  });
}
