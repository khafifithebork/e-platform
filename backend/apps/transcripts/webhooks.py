"""The transcription provider's callback.

Invariant 8, the same four steps M5 proved: verify the signature, insert a
``WebhookEvent``, enqueue a task, return 200. No business logic here.

**The `provider` value is namespaced.** The idempotency table is shared with
media (ADR-012 §3) and both fakes are called ``fake``, so writing the bare
name would put two different providers' events in one namespace under a unique
constraint on ``(provider, provider_event_id)``. Two ids would only have to
collide once for a transcription callback to be silently discarded as a
duplicate media event — and the symptom would be a lesson that never gets
subtitles, with a 200 in the log saying it was handled.

A forged callback here is worse than a forged media event: it rewrites the
words a learner reads as the lesson. That is why the signature is checked
before anything is recorded, and why the fake signs for real.
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
from apps.transcripts.providers.base import WebhookSignatureInvalid
from apps.transcripts.providers.fake import transcription_provider
from apps.transcripts.tasks import apply_transcription_callback

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "HTTP_X_WEBHOOK_SIGNATURE"


def namespaced(provider_name: str) -> str:
    """How a transcription provider appears in the shared webhook table."""
    return f"transcription:{provider_name}"


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["webhooks"])
class TranscriptionWebhookView(APIView):
    """Receive one completed (or failed) transcription job."""

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
        summary="Transcription provider callback",
    )
    def post(self, request):
        payload = request.body
        signature = request.META.get(SIGNATURE_HEADER, "")
        provider = transcription_provider()

        try:
            provider.verify_webhook(payload=payload, signature=signature)
        except WebhookSignatureInvalid:
            logger.warning("transcription_webhook_signature_invalid")
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            result = provider.parse_webhook(payload=payload)
        except (KeyError, ValueError):
            logger.warning("transcription_webhook_unparseable")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                record = WebhookEvent.objects.create(
                    provider=namespaced(provider.name),
                    # The job id is the event id here: a provider reports once
                    # per job, so it is the natural idempotency key and needs
                    # no derivation of our own.
                    provider_event_id=result.job_id,
                    event_type=f"transcription.{result.status.lower()}",
                    payload=result.payload,
                )
        except IntegrityError:
            logger.info("transcription_webhook_duplicate", extra={"job_id": result.job_id})
            return Response(status=status.HTTP_200_OK)

        transaction.on_commit(lambda: apply_transcription_callback.delay(str(record.pk)))

        return Response(status=status.HTTP_200_OK)
