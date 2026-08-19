"""Drive the fake billing provider from the command line.

architecture.md §10 M4 specifies a fake provider "driven by management
commands". This is that driver, and it is the only way to move a subscription
in M4 — there is deliberately no HTTP endpoint through which a user can grant
themselves a subscription.

One command with subcommands rather than six commands, because they share
every argument and the alternative is six files differing by one line.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.entitlements import services
from apps.entitlements.providers.fake import FakeBillingProvider

ACTIONS = ("start", "renew", "fail-payment", "cancel", "expire")


class Command(BaseCommand):
    help = "Move a subscription through its lifecycle using the fake provider."

    def add_arguments(self, parser) -> None:
        parser.add_argument("action", choices=ACTIONS)
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--trial-days",
            type=int,
            default=None,
            help="start only: begin as a trial of this many days.",
        )
        parser.add_argument(
            "--immediately",
            action="store_true",
            help="cancel only: end access now instead of at the period end.",
        )

    def handle(self, *args, **options) -> None:
        try:
            user = User.objects.get(email__iexact=options["email"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with email {options['email']}.") from exc

        provider = FakeBillingProvider()
        action = options["action"]

        try:
            subscription = self._run(action, user, provider, options)
        except services.NoLiveSubscription as exc:
            raise CommandError(f"{user.email} has no live subscription.") from exc
        except services.SubscriptionTransitionError as exc:
            raise CommandError(f"Refused: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"{user.email}: {subscription.status}, "
                f"period ends {subscription.current_period_end.isoformat()}"
            )
        )

    def _run(self, action: str, user, provider, options):
        if action == "start":
            return services.start_subscription(
                user=user, provider=provider, trial_days=options["trial_days"]
            )

        subscription = services.live_subscription(user=user)

        if action == "renew":
            return services.renew(subscription=subscription, provider=provider)
        if action == "fail-payment":
            return services.fail_payment(subscription=subscription, provider=provider)
        if action == "cancel":
            return services.cancel(
                subscription=subscription,
                provider=provider,
                immediately=options["immediately"],
            )
        return services.expire(subscription=subscription)
