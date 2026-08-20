"""Transcription routes.

The callback is called by the provider, not a browser: unauthenticated, and
the signature is the authentication (invariant 8).
"""

from django.urls import path

from apps.transcripts.webhooks import TranscriptionWebhookView

app_name = "transcripts"

urlpatterns = [
    path(
        "webhooks/transcription/",
        TranscriptionWebhookView.as_view(),
        name="transcription-webhook",
    ),
]
