"""Django Admin for entitlements.

Unrouted, like the catalogue's (ADR-008 §5): ``config/urls.py`` does not route
``admin/`` until M10 hardens it. Registering the classes means the surface is
built and tested; exposing it is a separate decision.

This is also **the only way an ``AccessOverride`` can be created**. The
resolver honours overrides and nothing else in the product grants one — no
endpoint, no management command — which is deliberate. A manual grant of free
access should require a human with administrator rights, leave a row naming
them, and expire by itself.
"""

from typing import ClassVar

from django.contrib import admin

from apps.entitlements.models import AccessOverride, Subscription, SubscriptionEvent


class SubscriptionEventInline(admin.TabularInline):
    """The history, beside the state it produced."""

    model = SubscriptionEvent
    extra = 0
    can_delete = False
    fields: ClassVar[list[str]] = ["created_at", "event_type", "from_status", "to_status"]
    readonly_fields: ClassVar[list[str]] = fields
    ordering: ClassVar[list[str]] = ["-created_at"]

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Read-only, and that is the point.

    Editing ``status`` here would be a second writer of subscription state,
    beside the provider and the service layer — exactly the two-writers
    problem §4.5 rule 3 rejects for a cached boolean, and worse, because it
    would leave no event explaining the change. Access is changed by granting
    an override, which is recorded.
    """

    list_display: ClassVar[list[str]] = [
        "user",
        "status",
        "current_period_end",
        "trial_end",
        "cancel_at_period_end",
        "provider",
    ]
    list_filter: ClassVar[list[str]] = ["status", "provider", "cancel_at_period_end"]
    search_fields: ClassVar[list[str]] = ["user__email", "provider_subscription_id"]
    list_select_related: ClassVar[list[str]] = ["user"]
    inlines: ClassVar[list] = [SubscriptionEventInline]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Deleting a subscription would erase the record of what somebody paid
        # for. Subscriptions end by expiring, not by disappearing.
        return False


@admin.register(AccessOverride)
class AccessOverrideAdmin(admin.ModelAdmin):
    """The one place free access can be granted by hand.

    ``granted_by`` is set from the session rather than chosen from a dropdown:
    an override whose grantor can be selected is an override that can be
    attributed to somebody else, which defeats the reason §5.2 wants a table
    instead of a flag.
    """

    list_display: ClassVar[list[str]] = ["user", "starts_at", "ends_at", "granted_by", "reason"]
    list_filter: ClassVar[list[str]] = ["starts_at", "ends_at"]
    search_fields: ClassVar[list[str]] = ["user__email", "reason"]
    list_select_related: ClassVar[list[str]] = ["user", "granted_by"]
    exclude: ClassVar[list[str]] = ["granted_by"]

    def save_model(self, request, obj, form, change) -> None:
        # From the session, never the form. There is no field to tamper with
        # because the field is not rendered.
        obj.granted_by = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None) -> bool:
        """Grants are not editable.

        An override that can be extended in place loses the history of what
        was originally granted. Extending access means granting another one,
        which leaves both rows on the record.
        """
        return False


@admin.register(SubscriptionEvent)
class SubscriptionEventAdmin(admin.ModelAdmin):
    """Append-only, like the course review trail. An editable audit log looks
    like evidence while being whatever the last person with access decided."""

    list_display: ClassVar[list[str]] = ["subscription", "event_type", "created_at"]
    list_filter: ClassVar[list[str]] = ["event_type"]
    search_fields: ClassVar[list[str]] = ["subscription__user__email"]
    list_select_related: ClassVar[list[str]] = ["subscription"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
