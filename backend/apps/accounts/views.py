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

from django.core.mail import send_mail
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    EmailOnlySerializer,
    RegisterSerializer,
    VerifyEmailSerializer,
)
from apps.accounts.services import (
    EmailAlreadyRegistered,
    InvalidVerificationToken,
    User,
    create_account,
    issue_email_verification,
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
