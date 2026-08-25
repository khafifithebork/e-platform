"""The audit log, readable and nothing else. ADR-018 §6.

architecture.md line 784 puts *audit inspection* in Django Admin rather than in
a custom API, and this is it. The detail view is where the whole row is
readable — including `metadata`, which the diagnostics API deliberately does
not render (see `AuditTrailEntrySerializer`).

Every mutation is denied at the `ModelAdmin`, and that is belt on top of
braces: `AuditLog.save` and `AuditLog.delete` already raise, as do the
queryset's `update` and `delete`. The registration matters anyway, because a
`ModelAdmin` with the defaults on is a surface that *offers* the buttons — and
a delete confirmation that ends in a 500 is a worse answer than a page that
never offered it.
"""

from typing import ClassVar

from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "created_at",
        "action",
        "actor_label",
        "target_type",
        "target_id",
        "ip_address",
    ]
    list_filter: ClassVar[list[str]] = ["action", "target_type"]
    # `actor_label` rather than `actor__email`: the label is what survives the
    # actor's deletion, so searching it finds rows the join no longer reaches.
    search_fields: ClassVar[list[str]] = ["actor_label", "target_id", "action"]
    date_hierarchy = "created_at"
    ordering: ClassVar[list[str]] = ["-created_at"]

    # Everything, so the detail view renders as text rather than as a form.
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "created_at",
        "actor",
        "actor_label",
        "action",
        "target_type",
        "target_id",
        "metadata",
        "ip_address",
    ]

    # Removes the bulk delete action, which `has_delete_permission` alone does
    # **not**: Django adds `delete_selected` from the site's action registry,
    # and it is the easiest way to lose history through a UI that otherwise
    # looks read-only.
    actions: ClassVar[None] = None

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
