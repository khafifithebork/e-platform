"""Authentication routes (architecture.md §6.2)."""

from django.urls import path

from apps.accounts.views import (
    DataExportView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
    csrf,
)

app_name = "accounts"

urlpatterns = [
    path("csrf/", csrf, name="csrf"),
    path("me/", MeView.as_view(), name="me"),
    # Under me/, because it is the same subject read a different way: the
    # signed-in account and nothing selectable.
    path("me/export/", DataExportView.as_view(), name="data-export"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
]
