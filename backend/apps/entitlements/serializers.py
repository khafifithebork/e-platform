"""I/O shapes for the entitlement admin surface. Format only (invariant 2)."""

from typing import ClassVar

from rest_framework import serializers

from apps.entitlements.models import AccessOverride, Subscription, SubscriptionEvent


class SubscriptionDiagnosticSerializer(serializers.ModelSerializer):
    """Includes `provider_subscription_id`, deliberately.

    It is the handle support needs to find the same subscription in the
    provider's own dashboard, and this endpoint is administrators only. It
    appears nowhere a subscriber can reach.
    """

    class Meta:
        model = Subscription
        fields: ClassVar[list[str]] = [
            "id",
            "status",
            "current_period_end",
            "trial_end",
            "cancel_at_period_end",
            "provider",
            "provider_subscription_id",
            "created_at",
        ]


class SubscriptionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionEvent
        fields: ClassVar[list[str]] = [
            "id",
            "event_type",
            "from_status",
            "to_status",
            "created_at",
        ]


class AccessOverrideSerializer(serializers.ModelSerializer):
    granted_by_email = serializers.EmailField(source="granted_by.email", read_only=True)

    class Meta:
        model = AccessOverride
        fields: ClassVar[list[str]] = [
            "id",
            "reason",
            "granted_by_email",
            "starts_at",
            "ends_at",
            "created_at",
        ]


class DiagnosticUserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)


class AccessDecisionSerializer(serializers.Serializer):
    allowed = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True)
    cta = serializers.CharField(read_only=True, allow_null=True)


class UserDiagnosticsSerializer(serializers.Serializer):
    """The answer to "why is this person's access wrong"."""

    user = DiagnosticUserSerializer(read_only=True)
    access = AccessDecisionSerializer(read_only=True)
    subscriptions = SubscriptionDiagnosticSerializer(many=True, read_only=True)
    events = SubscriptionEventSerializer(many=True, read_only=True)
    overrides = AccessOverrideSerializer(many=True, read_only=True)


class AccessOverrideGrantSerializer(serializers.Serializer):
    """What an administrator sends to grant access.

    A duration rather than an end date, so an override cannot be created
    already expired and cannot be created without an end. The upper bound is
    `settings.ACCESS_OVERRIDE_MAX_DAYS` — read at validation time rather than
    captured at import, so a deployment can lower it without a code change.
    """

    days = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_days(self, value: int) -> int:
        from django.conf import settings

        if value > settings.ACCESS_OVERRIDE_MAX_DAYS:
            raise serializers.ValidationError(
                f"An override runs at most {settings.ACCESS_OVERRIDE_MAX_DAYS} days."
            )
        return value


class RefundRequestSerializer(serializers.Serializer):
    """What an administrator sends to issue a refund.

    **No amount, deliberately.** `Subscription` holds no money — providers/base
    says so and gives the reason — and whether a provider supports partial
    refunds, in what currency, within what window, is a provider fact this
    project does not yet have (§11 #1). A field accepting an amount would be
    asking for something nothing can honestly use, and would have to change
    shape once M8 knows the answer. It arrives with the provider.

    Which leaves the reason, which is ours and is required for the same reason
    an override's is: the row exists to answer *why*, six weeks later, to
    somebody who was not there.
    """

    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
