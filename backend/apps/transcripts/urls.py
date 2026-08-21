"""Transcription routes.

The callback is called by the provider, not a browser: unauthenticated, and
the signature is the authentication (invariant 8).
"""

from django.urls import path, re_path

from apps.transcripts.views import (
    LessonTranscriptPanelView,
    LessonTranscriptView,
    SegmentEditView,
    TranscriptDetailView,
    TranscriptReviewView,
)
from apps.transcripts.webhooks import TranscriptionWebhookView

app_name = "transcripts"

urlpatterns = [
    path(
        "lessons/<uuid:pk>/transcript.vtt",
        LessonTranscriptView.as_view(),
        name="lesson-vtt",
    ),
    # Beside the .vtt route, not instead of it: a `<track>` element consumes
    # one and a panel needs the other.
    path(
        "lessons/<uuid:pk>/transcript/",
        LessonTranscriptPanelView.as_view(),
        name="lesson-transcript",
    ),
    path("transcripts/<uuid:pk>/", TranscriptDetailView.as_view(), name="detail"),
    path("transcript-segments/<uuid:pk>/", SegmentEditView.as_view(), name="segment-edit"),
    # The actions are enumerated in the pattern, so an unknown one is a 404
    # by routing rather than a KeyError reaching the client as a 500.
    re_path(
        r"^transcripts/(?P<pk>[0-9a-f-]{36})/(?P<action>start-review|approve|reopen)/$",
        TranscriptReviewView.as_view(),
        name="review",
    ),
    path(
        "webhooks/transcription/",
        TranscriptionWebhookView.as_view(),
        name="transcription-webhook",
    ),
]
