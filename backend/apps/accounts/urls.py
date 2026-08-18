"""Authentication routes (architecture.md §6.2)."""

from django.urls import path

from apps.accounts.views import (
    LoginView,
    LogoutView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
    csrf,
)

app_name = "accounts"

urlpatterns = [
    path("csrf/", csrf, name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
]
