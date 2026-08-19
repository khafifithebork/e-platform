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
