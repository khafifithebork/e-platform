"""How a refusal reaches the client.

The resolver decides and says why; this turns that into an HTTP answer without
losing the why. §4.5 rule 2 is the whole point — the interface has to
distinguish "log in", "your payment failed" and "upgrade", and a bare 403
forces the frontend to re-derive which one it is, putting entitlement logic in
a second place.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException

from apps.entitlements.resolver import AccessDecision


class EntitlementDenied(APIException):
    """403 with a reason attached.

    One problem type for every entitlement refusal, not one per reason. The
    ``type`` says what kind of problem this is — clients branch on it per
    ADR-004 — and ``reason`` says which case, from a stable enum. Splitting the
    type per reason would mean every new reason is a breaking change to
    anything matching on unknown types.

    403 even for LOGIN_REQUIRED, which reads like a 401. Two reasons: §6.3
    specifies 403 for entitlement denial, and DRF downgrades 401 to 403 anyway
    whenever no authenticator offers a ``WWW-Authenticate`` header —
    SessionAuthentication offers none (ADR-004). The status would therefore be
    403 whatever we intended, so the type and reason are what carry the
    meaning.
    """

    status_code = status.HTTP_403_FORBIDDEN
    problem_type = "/problems/entitlement-denied"
    default_detail = "You do not have access to this content."

    def __init__(self, decision: AccessDecision) -> None:
        if decision.allowed:
            # A decision that allowed access cannot be a refusal. Raising here
            # turns a caller's inverted condition into a loud failure rather
            # than a 403 shown to somebody who has paid.
            raise ValueError("EntitlementDenied requires a denial, not an allowance.")

        super().__init__(detail=self.default_detail)
        self.decision = decision
        # Read by the Problem Details handler and merged into the document.
        self.extensions = {"reason": str(decision.reason), "cta": decision.cta}
