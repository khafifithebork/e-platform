"""HTTP concerns only.

Invariant 2 says a view should be readable in ten seconds and must not contain
an `if` about business state. These take a request, hand it to a service, and
choose a status code.

The one thing they do decide is *what to say* — and on these endpoints that is
a security control in its own right, not presentation. §7.1 lists account
enumeration as a real threat: an attacker with a list of addresses should not
be able to learn which ones have accounts here.
"""

from typing import ClassVar

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.core.mail import send_mail
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_safe
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    EmailOnlySerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    RegisterSerializer,
    VerifyEmailSerializer,
)
from apps.accounts.services import (
    EmailAlreadyRegistered,
    IncorrectPassword,
    InvalidPasswordResetToken,
    InvalidVerificationToken,
    User,
    change_password,
    create_account,
    issue_email_verification,
    issue_password_reset,
    reset_password,
    verify_email,
)

# One response for every registration outcome. Returned whether the account was
# created, the address was already taken, or nothing happened at all.
REGISTRATION_ACCEPTED = {
    "detail": "If that address can be registered, a verification email is on its way."
}

RESEND_ACCEPTED = {
    "detail": "If that address has an unverified account, a verification email is on its way."
}


def _send_verification_email(*, email: str, token: str) -> None:
    """Deliver the raw token.

    Django's email framework rather than a provider adapter: this speaks SMTP,
    which Mailpit serves locally and Resend serves in production, so invariant
    4 is not engaged until we call a vendor's HTTP API.

    A plain-text body for now. Templates and branding arrive with the
    notifications app.
    """
    send_mail(
        subject="Verify your email address",
        message=(
            "Welcome. Use this token to verify your email address:\n\n"
            f"{token}\n\n"
            "It expires in 24 hours. If you did not create an account, "
            "you can ignore this message."
        ),
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


@extend_schema(
    request=RegisterSerializer,
    responses={
        202: OpenApiResponse(
            description="Accepted. Identical whether or not the address was free."
        ),
        400: OpenApiResponse(description="Malformed input or a password that fails validation."),
    },
    summary="Register an account",
)
class RegisterView(APIView):
    """Create an account and send a verification email.

    Always answers 202 with the same body. That is abuse case 1: a differing
    status, body, or field error would let someone test an address list against
    this endpoint and learn who has an account here.

    The response is 202 rather than 201 because the meaningful part — the email
    — has not happened yet, and because 201 with a Location header would imply
    a resource the caller may now fetch.
    """

    permission_classes: ClassVar[list] = [AllowAny]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            create_account(email=email, password=serializer.validated_data["password"])
        except EmailAlreadyRegistered:
            # Deliberately silent. The address is taken, and saying so is
            # exactly the disclosure this endpoint exists to avoid. A courtesy
            # "someone tried to register with your address" email is the usual
            # next refinement and belongs with the notifications app.
            return Response(REGISTRATION_ACCEPTED, status=status.HTTP_202_ACCEPTED)

        _send_verification_email(
            email=email,
            token=issue_email_verification(user=User.objects.get(email=email)),
        )

        return Response(REGISTRATION_ACCEPTED, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=EmailOnlySerializer,
    responses={
        202: OpenApiResponse(description="Accepted. Identical for unknown and verified addresses.")
    },
    summary="Resend the verification email",
)
class ResendVerificationView(APIView):
    """Issue a fresh verification token.

    Same uniform response for the same reason, and it covers three cases that
    must look identical: no such account, an account already verified, and a
    genuine resend.
    """

    permission_classes: ClassVar[list] = [AllowAny]
    throttle_scope = "resend_verification"

    def post(self, request):
        serializer = EmailOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email=serializer.validated_data["email"]).first()

        if user is not None and not user.is_email_verified:
            _send_verification_email(
                email=user.email,
                token=issue_email_verification(user=user),
            )

        return Response(RESEND_ACCEPTED, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=VerifyEmailSerializer,
    responses={
        200: OpenApiResponse(description="Email address verified."),
        400: OpenApiResponse(
            description="Token unknown, expired or already used — deliberately not distinguished."
        ),
    },
    summary="Verify an email address",
)
class VerifyEmailView(APIView):
    """Consume a verification token.

    Unlike registration this one may fail visibly: the caller is holding a
    token and needs to know it did not work. It still says only that the token
    is invalid, never which of unknown, expired or already-used applies —
    telling them would turn a failed guess into information.
    """

    permission_classes: ClassVar[list] = [AllowAny]
    throttle_scope = "verify_email"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            verify_email(token=serializer.validated_data["token"])
        except InvalidVerificationToken:
            return Response(
                {"detail": "That verification link is not valid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Email address verified."}, status=status.HTTP_200_OK)


# One answer for every failed sign-in. A wrong password and an address with no
# account must be indistinguishable, or the endpoint becomes a way to test an
# address list against the user table.
LOGIN_REFUSED = {"detail": "Those credentials are not valid."}


@extend_schema(
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(description="Signed in. A session cookie is set."),
        400: OpenApiResponse(
            description="Credentials refused, or the account is locked. Deliberately one answer."
        ),
    },
    summary="Sign in",
)
class LoginView(APIView):
    """Establish a session.

    `authenticate` runs through AxesStandaloneBackend first, so a locked
    account fails here exactly as a wrong password does — and says the same
    thing. Telling a caller "this account is locked" would confirm the address
    exists and tell them their guessing worked well enough to matter.

    Deliberately not CSRF-exempt. Forcing a victim's browser to sign in as the
    attacker is a real attack: everything they do next is recorded against the
    wrong account.
    """

    permission_classes: ClassVar[list] = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        if user is None:
            return Response(LOGIN_REFUSED, status=status.HTTP_400_BAD_REQUEST)

        # Django cycles the session key here, which is what defeats session
        # fixation: a cookie planted before sign-in is worthless afterwards.
        login(request, user)

        return Response({"detail": "Signed in."}, status=status.HTTP_200_OK)


@extend_schema(
    request=None,
    responses={200: OpenApiResponse(description="Signed out. Idempotent.")},
    summary="Sign out",
)
class LogoutView(APIView):
    """Destroy the session.

    Idempotent, and permitted while unauthenticated: a client retrying after a
    timeout should not receive an error for succeeding twice, and refusing an
    anonymous caller would leak whether their session was still alive.
    """

    permission_classes: ClassVar[list] = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"detail": "Signed out."}, status=status.HTTP_200_OK)


@require_safe
@ensure_csrf_cookie
def csrf(request):
    """Hand the browser a CSRF token.

    The frontend cannot POST anything until it has one, and Django only sets
    the cookie when a view asks for it. A plain Django view rather than a DRF
    one so it sits outside deny-by-default and the throttles — it grants
    nothing and reveals nothing.
    """
    from django.http import JsonResponse

    return JsonResponse({"detail": "CSRF cookie set."})


PASSWORD_RESET_ACCEPTED = {"detail": "If that address has an account, a reset link is on its way."}


def _send_password_reset_email(*, email: str, token: str) -> None:
    send_mail(
        subject="Reset your password",
        message=(
            "Use this token to set a new password:\n\n"
            f"{token}\n\n"
            "It expires in one hour. If you did not ask to reset your "
            "password, you can ignore this message — nothing has changed."
        ),
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


@extend_schema(
    request=EmailOnlySerializer,
    responses={202: OpenApiResponse(description="Accepted. Identical for unknown addresses.")},
    summary="Request a password reset",
)
class PasswordResetView(APIView):
    """Send a reset link.

    Always 202. §6.2 is explicit that this must never reveal whether an account
    exists, and a reset endpoint is the most attractive enumeration oracle in
    any application because it is designed to be used by people who are locked
    out and therefore unauthenticated.
    """

    permission_classes: ClassVar[list] = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = EmailOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email=serializer.validated_data["email"]).first()
        if user is not None:
            _send_password_reset_email(email=user.email, token=issue_password_reset(user=user))

        return Response(PASSWORD_RESET_ACCEPTED, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=PasswordResetConfirmSerializer,
    responses={
        200: OpenApiResponse(description="Password changed. All sessions are invalidated."),
        400: OpenApiResponse(description="Token invalid, or the new password was rejected."),
    },
    summary="Set a new password with a reset token",
)
class PasswordResetConfirmView(APIView):
    permission_classes: ClassVar[list] = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reset_password(
                token=serializer.validated_data["token"],
                new_password=serializer.validated_data["new_password"],
            )
        except InvalidPasswordResetToken:
            return Response(
                {"detail": "That reset link is not valid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Password changed. Please sign in again."},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    request=PasswordChangeSerializer,
    responses={
        200: OpenApiResponse(description="Password changed."),
        400: OpenApiResponse(description="Current password wrong, or new password rejected."),
    },
    summary="Change your password",
)
class PasswordChangeView(APIView):
    """Change the password of the signed-in user.

    The only endpoint here that requires authentication, so it uses the
    project default rather than AllowAny.
    """

    throttle_scope = "password_change"

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            change_password(
                user=request.user,
                current_password=serializer.validated_data["current_password"],
                new_password=serializer.validated_data["new_password"],
            )
        except IncorrectPassword:
            return Response(
                {"detail": "Your current password is not correct."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Without this the caller is signed out of the browser they just used,
        # because changing the password rotates the session auth hash. Other
        # sessions still die, which is the intent.
        update_session_auth_hash(request, request.user)

        return Response({"detail": "Password changed."}, status=status.HTTP_200_OK)
