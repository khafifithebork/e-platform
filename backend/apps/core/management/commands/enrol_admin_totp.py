"""Enrol an administrator's authenticator app.

**This exists because of a bootstrap problem.** The admin site is where you
would manage OTP devices, and the admin site cannot be reached without one. A
command is the only way in that does not involve opening a temporary hole.

It prints a secret to a terminal. That is the standard enrolment flow — the
secret has to reach an authenticator app somehow — but it makes the output
sensitive: do not run this into a log, a shared terminal, or a CI job. Nothing
here writes the secret anywhere but stdout.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create a TOTP device for a staff account and print its enrolment QR code."

    def add_arguments(self, parser) -> None:
        parser.add_argument("email", help="The staff account to enrol.")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace an existing device. The old one stops working immediately.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        email = options["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist as exc:
            raise CommandError(f"No account for {email}.") from exc

        if not user.is_staff:
            # Enrolling a non-staff account would create a device that grants
            # nothing while suggesting otherwise. `is_staff` is granted
            # deliberately in this codebase — see accounts.models.
            raise CommandError(f"{email} is not staff, so a device would grant nothing.")

        existing = TOTPDevice.objects.filter(user=user)
        if existing.exists() and not options["replace"]:
            raise CommandError(
                f"{email} already has a device. Re-run with --replace to issue a new one, "
                "which stops the old one working immediately."
            )
        existing.delete()

        device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)

        self.stdout.write(self.style.WARNING("Scan this once, then clear your terminal."))
        self._print_qr(device.config_url)
        self.stdout.write("Or enter the URI by hand:")
        self.stdout.write(device.config_url)
        self.stdout.write(self.style.SUCCESS(f"Enrolled {email}."))

    def _print_qr(self, uri: str) -> None:
        """Render the QR as text, so no image file lands on disk holding a
        secret nobody remembers to delete."""
        import qrcode

        code = qrcode.QRCode(border=1)
        code.add_data(uri)
        code.make(fit=True)
        code.print_ascii(out=self.stdout)
