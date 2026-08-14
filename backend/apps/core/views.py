"""Infrastructure endpoints.

Not part of the product API: nothing here lives under ``/api/v1/`` or appears
in the OpenAPI schema.
"""

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe


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
