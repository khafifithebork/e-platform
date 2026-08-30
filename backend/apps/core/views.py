"""Infrastructure endpoints.

Not part of the product API: nothing here lives under ``/api/v1/`` or appears
in the OpenAPI schema.
"""

import json
import logging
import secrets

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_safe

from apps.core.metrics import collect as collect_metrics
from apps.core.metrics import render as render_metrics


@require_safe
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness. Answers one question: is this process serving HTTP?

    It deliberately does **not** check Postgres or Redis. That is readiness,
    and conflating the two is harmful rather than merely imprecise — a liveness
    probe that fails during a thirty-second database blip invites the
    orchestrator to kill and reschedule containers that were seconds from
    recovering, turning a dependency wobble into an outage. A separate
    readiness endpoint can be added when a deployment exists that consumes one.

    This is a plain Django view rather than a DRF one, for two reasons that are
    both failure modes rather than preferences:

    - DRF defaults to ``IsAuthenticated`` (see REST_FRAMEWORK in base settings),
      so a DRF view here would answer 403 forever and the platform would
      conclude the service was dead.
    - DRF throttling counts anonymous requests at 60/min per IP. Sharing that
      bucket would let a busy origin throttle its own health check, and the
      platform would then kill containers that were serving traffic correctly.

    Known gotcha, not solved here: this still passes through Django's
    ALLOWED_HOSTS check. A probe that connects by container IP rather than
    hostname will get a 400 before reaching this view. Configure the platform
    check to send a Host header that ALLOWED_HOSTS accepts.
    """
    # no-store, not no-cache: a cached 200 at the edge would keep reporting
    # health for a process that has been dead for minutes.
    return JsonResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})


# A violation report is a browser telling us a page tried to do something the
# policy forbade. It is also **an unauthenticated POST body from anyone on the
# internet**, which is the fact that shapes everything below: the endpoint is
# public by necessity — browsers send these with no credentials — so it is a
# free write into our logs unless it is bounded.
MAX_REPORT_BYTES = 8_192

# Only what is worth reading. A report carries more than this, and the rest is
# either noise or a URL we would rather not copy into a log line.
REPORTED_FIELDS = ("document-uri", "violated-directive", "effective-directive", "blocked-uri")

# `blocked-uri` and `document-uri` are URLs, and a URL can carry a token in its
# query string. Truncated hard rather than parsed: a parser here would be one
# more thing accepting hostile input.
MAX_FIELD_LENGTH = 200

csp_logger = logging.getLogger("apps.core.csp")


@csrf_exempt
@require_POST
def csp_report(request: HttpRequest) -> HttpResponse:
    """Receive a Content-Security-Policy violation report.

    M12 shipped the policy report-only with nowhere to report to, because
    inventing an endpoint would have put a fabricated URL in the header of
    every response. This is that endpoint.

    **Logged, never stored.** ADR-020 §8 declined an email audit table on the
    same reasoning and it holds harder here: the sender is anonymous and
    unauthenticated, so a table would be a way for anyone to write unbounded
    rows into our database. A log line is rate-limited by the platform, ages
    out on its own, and nothing queries it to make a decision.

    **CSRF-exempt because it must be.** Browsers post violation reports with no
    CSRF token and no session; requiring one would mean receiving nothing,
    which is indistinguishable from a policy with no violations.

    Answers 204 to everything it accepts and everything it rejects. A browser
    does nothing with the status, and a distinguishable rejection would tell
    somebody probing exactly where the size limit is.
    """
    if len(request.body) > MAX_REPORT_BYTES:
        # Dropped silently. An oversized report is either a bug or an attempt
        # to write a large log line, and neither deserves a reply that
        # confirms the limit.
        return HttpResponse(status=204)

    try:
        payload = json.loads(request.body or b"{}")
        report = payload.get("csp-report", payload)
        if not isinstance(report, dict):
            raise ValueError("not an object")
    except (ValueError, UnicodeDecodeError):
        # Malformed JSON from an anonymous source is not an error worth an
        # error level. It is the internet.
        return HttpResponse(status=204)

    csp_logger.info(
        "csp_violation",
        extra={
            "event": "csp_violation",
            **{
                field.replace("-", "_"): str(report.get(field, ""))[:MAX_FIELD_LENGTH]
                for field in REPORTED_FIELDS
            },
        },
    )
    return HttpResponse(status=204)


# The metrics endpoint's shared secret. Empty means the endpoint does not
# exist — which is the state of this repository, because there is no scraper
# yet (M14 T6, ADR-028 §3).
#
# A token rather than a session or a role, because the caller is a scraper: it
# holds no account, cannot log in, and must present the same credential on
# every request forever. That is what a bearer token is for.
_BEARER = "Bearer "


@require_safe
def metrics(request: HttpRequest) -> HttpResponse:
    """Prometheus exposition of the operational gauges.

    **A plain Django view, not DRF, and `healthz` learned why the hard way.**
    DRF defaults to ``IsAuthenticated`` here, so a scraper would receive 403
    forever; and DRF throttles anonymous requests at 60/min per IP, which a
    scrape every 15 seconds from one address would eventually trip. Both
    failures look like the endpoint working until somebody reads a dashboard.

    **404 when unconfigured, 403 when the token is wrong.** These say different
    things on purpose. Unconfigured means the feature is off and the endpoint
    genuinely is not there. A wrong token means it is there and the caller got
    it wrong, which is the fact an operator needs when a scraper goes quiet —
    and hiding it would only hide the endpoint from somebody who already knows
    the path. ADR-019 §5 settled the same question for the admin site the same
    way: refuse clearly rather than pretend.

    Comparison is constant-time. A token compared with ``==`` leaks its prefix
    to anyone who can measure a few thousand requests, and this one guards a
    read of operational data.
    """
    expected = settings.METRICS_TOKEN
    if not expected:
        raise Http404

    header = request.headers.get("Authorization", "")
    presented = header[len(_BEARER) :] if header.startswith(_BEARER) else ""

    if not secrets.compare_digest(presented, expected):
        return HttpResponse("forbidden\n", status=403, content_type="text/plain")

    body = render_metrics(collect_metrics())

    # `version=0.0.4` is the exposition format's own version, not ours. Scrapers
    # content-negotiate on it, and omitting it makes some of them guess.
    return HttpResponse(
        body,
        content_type="text/plain; version=0.0.4; charset=utf-8",
        # A cached scrape is a lie with a timestamp on it.
        headers={"Cache-Control": "no-store"},
    )
