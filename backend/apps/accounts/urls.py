"""Authentication routes (architecture.md §6.2)."""

from django.urls import path

from apps.accounts.views import RegisterView, ResendVerificationView, VerifyEmailView

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
]
