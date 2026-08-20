"""The video provider's webhook receiver.

Invariant 8 fixes the shape, and the order is the substance of it:

1. **Verify the signature.** Before anything is recorded. An unverified
   webhook is an unauthenticated write to media state, and recording it first
   would let anyone fill the idempotency table with ids the real provider
   would then be refused for — a denial of service made of our own guard.
2. **Insert a ``WebhookEvent``.** The unique constraint is the idempotency
   mechanism. A duplicate loses at the database, not at an ``if``.
3. **Enqueue a task.**
4. **Return 200.**

**No business logic here.** The handler does not know what a media asset is.
That is not tidiness: a provider retries on any non-2xx, so anything that can
fail in this function turns a transient error into a retry storm, and anything
slow here is a request the provider may time out and repeat.

A duplicate returns **200 without reprocessing**. A provider that receives an
error assumes we did not get the event and sends it again, so answering
anything else to a replay guarantees more replays.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import WebhookEvent
from apps.media_assets.providers.fake_video import video_provider
from apps.media_assets.providers.video import WebhookSignatureInvalid
from apps.media_assets.tasks import apply_media_webhook

logger = logging.getLogger(__name__)

# The header the provider signs with. Named in one place because M8's adapter
# will use a different one, and the view should not know which.
SIGNATURE_HEADER = "HTTP_X_WEBHOOK_SIGNATURE"


def namespaced(provider_name: str) -> str:
    """How a video provider appears in the shared webhook table.

    Namespaced because the table is shared with transcription (ADR-012 §3) and
    both fakes are called ``fake``. Without a prefix two providers' events sit
    in one namespace under a unique constraint on
    ``(provider, provider_event_id)``, and one id collision would discard one
    provider's event as a duplicate of the other's — answering 200 while doing
    nothing.
    """
    return f"video:{provider_name}"


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["webhooks"])
class VideoWebhookView(APIView):
    """Receive one event from the video provider.

    Unauthenticated by design — the provider has no session and no CSRF token.
    **The signature is the authentication**, which is why it is checked first
    and why the fake verifies for real rather than accepting anything.

    Throttled, and safe to throttle: a provider retries on any non-2xx, so a
    429 delays an event rather than losing it. Unthrottled, this is an
    unauthenticated endpoint anyone can post to, and the HMAC check is the
    only thing standing between them and our worker.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "webhook"

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="Accepted, or already seen."),
            400: OpenApiResponse(description="Malformed payload."),
            401: OpenApiResponse(description="Signature missing or invalid."),
        },
        summary="Video provider webhook",
    )
    def post(self, request):
        payload = request.body
        signature = request.META.get(SIGNATURE_HEADER, "")
        provider = video_provider()

        # 1. Verify, before the payload has touched anything.
        try:
            provider.verify_webhook(payload=payload, signature=signature)
        except WebhookSignatureInvalid:
            logger.warning("webhook_signature_invalid", extra={"provider": provider.name})
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        # Parsing is the only other thing that can reasonably fail, and a
        # payload we cannot read is not worth a retry — the provider would
        # send the same bytes again.
        try:
            event = provider.parse_webhook(payload=payload)
        except (KeyError, ValueError):
            logger.warning("webhook_unparseable", extra={"provider": provider.name})
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # 2. Insert. The unique constraint decides whether this is new.
        try:
            with transaction.atomic():
                record = WebhookEvent.objects.create(
                    provider=namespaced(provider.name),
                    provider_event_id=event.event_id,
                    event_type=event.event_type,
                    payload=event.payload,
                )
        except IntegrityError:
            # Seen before. 200 without reprocessing: a provider that gets an
            # error assumes we missed the event and sends it again.
            logger.info(
                "webhook_duplicate",
                extra={"provider": provider.name, "event_id": event.event_id},
            )
            return Response(status=status.HTTP_200_OK)

        # 3. Enqueue, after commit so the worker cannot read a row that is not
        # there yet — the same ordering the upload path needs.
        transaction.on_commit(lambda: apply_media_webhook.delay(str(record.pk)))

        # 4. 200. Nothing about media has happened yet, and that is correct:
        # the provider is told we have the event, not that we have acted on it.
        return Response(status=status.HTTP_200_OK)
